#!/usr/bin/env python3
"""Create and remove temporary Uptime Kuma maintenance windows.

This helper intentionally executes the Kuma API call from inside the running
SWAG container. SWAG already has the uptime-kuma-api Python package installed
and already carries the Uptime Kuma credentials used by the auto-sync mod.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


KUMA_ENV_KEYS = (
    "UPTIME_KUMA_URL",
    "UPTIME_KUMA_USERNAME",
    "UPTIME_KUMA_PASSWORD",
    "UPTIME_KUMA_USER",
    "UPTIME_KUMA_PASS",
    "UPTIME_KUMA_PUBLIC_DOMAIN",
    "URL",
)


INNER_SCRIPT = r"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from urllib.parse import urlparse

import socketio


FALSE_VALUES = {"0", "false", "no", "off"}


def log(message: str) -> None:
    print(message, file=sys.stderr)


def normalize(value: object) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def monitor_swag_tag(monitor: dict) -> str:
    for tag in monitor.get("tags") or []:
        if tag.get("name") == "swag":
            return str(tag.get("value") or "")
    return ""


def configured_public_domain() -> str:
    raw = os.environ.get("UPTIME_KUMA_PUBLIC_DOMAIN") or os.environ.get("URL") or ""
    raw = raw.strip()
    if "://" in raw:
        raw = urlparse(raw).hostname or raw
    return raw.split(":")[0].lower().lstrip(".")


def is_public_domain_monitor(monitor: dict, domain: str) -> bool:
    if not domain:
        return False

    host = urlparse(str(monitor.get("url") or "")).hostname
    if not host:
        return False

    host = host.lower()
    return host == domain or host.endswith("." + domain)


def selected_monitors(monitors: list[dict], targets: list[str]) -> list[dict]:
    target_names = set()
    target_norms = set()

    for target in targets:
        target = target.strip("/")
        basename = target.rsplit("/", 1)[-1]
        for value in {target, basename}:
            if value:
                target_names.add(value.lower())
                target_norms.add(normalize(value))

    include_all = bool(target_names.intersection({"*", "all", "docker", "docker-desktop", "nightly"}))
    domain = configured_public_domain()
    include_public = "swag" in target_names or "swag" in target_norms
    matched: dict[int, dict] = {}

    for monitor in monitors:
        if monitor.get("active", True) in (False, 0, "0"):
            continue

        if include_all:
            matched[int(monitor["id"])] = monitor
            continue

        if str(monitor.get("type") or "").lower() == "group":
            continue

        swag_tag = monitor_swag_tag(monitor)
        tag_match = swag_tag.lower() in target_names or normalize(swag_tag) in target_norms
        name_match = normalize(monitor.get("name")) in target_norms
        public_match = include_public and is_public_domain_monitor(monitor, domain)

        if tag_match or name_match or public_match:
            matched[int(monitor["id"])] = monitor

    return [matched[key] for key in sorted(matched)]


def socket_call(sio: socketio.Client, event: str, data=None, timeout: int = 30):
    response = sio.call(event, data, timeout=timeout)
    if isinstance(response, dict) and response.get("ok") is False:
        raise RuntimeError(response.get("msg") or f"{event} failed")
    return response


def wait_for_event(events: dict, event: str, timeout: int = 15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if event in events:
            return events[event]
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {event}")


def connect() -> tuple[socketio.Client, dict] | None:
    url = os.environ.get("UPTIME_KUMA_URL")
    username = os.environ.get("UPTIME_KUMA_USERNAME") or os.environ.get("UPTIME_KUMA_USER")
    password = os.environ.get("UPTIME_KUMA_PASSWORD") or os.environ.get("UPTIME_KUMA_PASS")

    if not url or not username or not password:
        log("missing UPTIME_KUMA_URL/username/password in the API container; skipping")
        return None

    url = url.rstrip("/")
    last_error = None
    for attempt in range(1, 4):
        events = {}
        sio = socketio.Client(logger=False, engineio_logger=False)

        @sio.on("monitorList")
        def on_monitor_list(data):
            events["monitorList"] = data

        try:
            sio.connect(f"{url}/socket.io/", wait_timeout=30)
            time.sleep(0.25)
            socket_call(sio, "login", {
                "username": username,
                "password": password,
                "token": "",
            })
            return sio, events
        except Exception as error:
            last_error = error
            log(f"Uptime Kuma socket login attempt {attempt} failed: {error}")
            try:
                sio.disconnect()
            except Exception:
                pass
            time.sleep(attempt)

    raise last_error


def get_monitors(sio: socketio.Client, events: dict) -> list[dict]:
    events.pop("monitorList", None)
    socket_call(sio, "getMonitorList")
    monitor_list = wait_for_event(events, "monitorList")
    return list(monitor_list.values())


def fmt(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def start(args: argparse.Namespace) -> int:
    connection = connect()
    if connection is None:
        return 0

    sio, events = connection
    try:
        monitors = selected_monitors(get_monitors(sio, events), args.targets)
        if not monitors:
            log("no matching Uptime Kuma monitors found; skipping")
            return 0

        ttl_minutes = max(args.ttl_minutes, 1)
        now = dt.datetime.now(dt.timezone.utc)
        start_at = now - dt.timedelta(minutes=1)
        end_at = now + dt.timedelta(minutes=ttl_minutes)
        target_names = ", ".join(monitor["name"] for monitor in monitors)
        title = args.title or f"Docker maintenance: {args.reason}"
        if len(title) > 120:
            title = title[:117] + "..."

        result = socket_call(sio, "addMaintenance", {
            "title": title,
            "description": f"Created automatically for {args.reason}. Targets: {target_names}",
            "strategy": "single",
            "active": True,
            "intervalDay": 1,
            "dateRange": [fmt(start_at), fmt(end_at)],
            "weekdays": [],
            "daysOfMonth": [],
            "timezoneOption": "UTC",
        })
        maintenance_id = int(result["maintenanceID"])
        socket_call(
            sio,
            "addMonitorMaintenance",
            (
                maintenance_id,
                [{"id": int(monitor["id"])} for monitor in monitors],
            ),
        )
        log(f"created maintenance {maintenance_id} for: {target_names}")
        print(maintenance_id)
        return 0
    finally:
        sio.disconnect()


def stop(args: argparse.Namespace) -> int:
    if not args.maintenance_id:
        return 0

    connection = connect()
    if connection is None:
        return 0

    sio, _events = connection
    try:
        socket_call(sio, "deleteMaintenance", int(args.maintenance_id))
        log(f"deleted maintenance {args.maintenance_id}")
        return 0
    finally:
        sio.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--ttl-minutes", type=int, default=120)
    start_parser.add_argument("--reason", default="Docker maintenance")
    start_parser.add_argument("--title")
    start_parser.add_argument("targets", nargs="+")

    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("maintenance_id", nargs="?")

    args = parser.parse_args()
    if args.command == "start":
        return start(args)
    if args.command == "stop":
        return stop(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
"""


FALSE_VALUES = {"0", "false", "no", "off"}


def maintenance_disabled() -> bool:
    return os.environ.get("DOCKER_DEPLOY_KUMA_MAINTENANCE", "true").lower() in FALSE_VALUES


def container_running(container: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return values

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value

    return values


def default_env_files() -> list[Path]:
    repo_dir = Path(__file__).resolve().parents[1]
    return [repo_dir / "swag" / ".env", repo_dir / "swag" / ".env.secret"]


def build_exec_env(env_files: list[str]) -> dict[str, str]:
    exec_env = os.environ.copy()
    configured_files = [Path(path) for path in env_files] if env_files else default_env_files()

    for env_file in configured_files:
        for key, value in parse_env_file(env_file).items():
            if value and not exec_env.get(key):
                exec_env[key] = value

    exec_env.setdefault("UPTIME_KUMA_URL", "http://uptime-kuma:3001/")
    return exec_env


def run_inside_container(container: str, inner_args: list[str], strict: bool, env_files: list[str]) -> int:
    if maintenance_disabled():
        print("Uptime Kuma maintenance disabled by DOCKER_DEPLOY_KUMA_MAINTENANCE", file=sys.stderr)
        return 0

    if not container_running(container):
        print(f"Uptime Kuma maintenance skipped; container {container!r} is not running", file=sys.stderr)
        return 1 if strict else 0

    exec_env = build_exec_env(env_files)
    env_args = []
    for key in KUMA_ENV_KEYS:
        if exec_env.get(key):
            env_args.extend(["-e", key])

    result = subprocess.run(
        ["docker", "exec", "-i", *env_args, container, "python3", "-", *inner_args],
        env=exec_env,
        input=dedent(INNER_SCRIPT),
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            f"Uptime Kuma maintenance command failed in {container!r} with exit code {result.returncode}",
            file=sys.stderr,
        )
        return result.returncode if strict else 0
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--container",
        default=os.environ.get("KUMA_API_CONTAINER", "swag"),
        help="Container that has uptime_kuma_api and Kuma credentials in its environment.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Env file to read for transient Kuma credentials. Defaults to swag/.env and swag/.env.secret.",
    )
    parser.add_argument("--strict", action="store_true", help="Return non-zero when maintenance setup fails.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Create a temporary maintenance window.")
    start.add_argument(
        "--ttl-minutes",
        type=int,
        default=int(os.environ.get("DOCKER_DEPLOY_KUMA_MAINTENANCE_TTL_MINUTES", "120")),
    )
    start.add_argument("--reason", default="Docker maintenance")
    start.add_argument("--title")
    start.add_argument("targets", nargs="+", help="Service folder/container names to put in maintenance.")

    stop = subparsers.add_parser("stop", help="Delete a temporary maintenance window.")
    stop.add_argument("maintenance_id", nargs="?")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "start":
        inner_args = [
            "start",
            "--ttl-minutes",
            str(args.ttl_minutes),
            "--reason",
            args.reason,
        ]
        if args.title:
            inner_args.extend(["--title", args.title])
        inner_args.extend(args.targets)
    elif args.command == "stop":
        if not args.maintenance_id:
            return 0
        inner_args = ["stop", args.maintenance_id]
    else:
        raise AssertionError(args.command)

    return run_inside_container(args.container, inner_args, args.strict, args.env_file)


if __name__ == "__main__":
    raise SystemExit(main())
