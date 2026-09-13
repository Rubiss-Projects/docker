#!/usr/bin/env python3
"""Mute Sunday Edge's expected availability/restart alerts during planned work.

Silences expire even if the caller or Docker host dies. Stopping maintenance
releases availability alerts immediately and keeps only restart notifications
muted for 35 minutes (the rule's 30-minute lookback plus evaluation/delivery time).
Credentials are read from the running Grafana container, never command arguments.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

SERVICE = "sunday-edge-dfs-simulator"
GRACE_MINUTES = 35
CREATOR = "docker-planned-maintenance"
API_PATH = "/api/alertmanager/grafana/api/v2"


def affected(targets: list[str]) -> bool:
    for target in targets:
        name = target.strip("/").rsplit("/", 1)[-1].lower()
        if name in {"all", "*", "docker", "docker-desktop", "nightly", "sunday-edge"} or name.startswith("sunday-edge-"):
            return True
    return False


def timestamp(value: dt.datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def matchers(window: str) -> list[dict]:
    return [
        {"name": "service", "value": SERVICE, "isRegex": False, "isEqual": True},
        {"name": "maintenance_window", "value": window, "isRegex": False, "isEqual": True},
    ]


class Grafana:
    def __init__(self):
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Env}}", "grafana"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        env = dict(item.split("=", 1) for item in json.loads(result.stdout))
        user = os.environ.get("GRAFANA_MAINTENANCE_USER", "rubiss")
        self.authorization = "Basic " + base64.b64encode(
            f"{user}:{env['GRAFANA_PASSWORD']}".encode()
        ).decode()

    def request(self, method: str, path: str, body=None):
        request = urllib.request.Request(
            "http://127.0.0.1:3000" + API_PATH + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": self.authorization, "Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read()
            return json.loads(data) if data else None


def start(api, ttl: int, reason: str, now=None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    ids = []
    try:
        for window, extra in [("wsl-nightly-availability", 0), ("wsl-nightly-restart", GRACE_MINUTES)]:
            result = api.request("POST", "/silences", {
                "matchers": matchers(window),
                "startsAt": timestamp(now),
                "endsAt": timestamp(now + dt.timedelta(minutes=ttl + extra)),
                "createdBy": CREATOR,
                "comment": f"Planned Sunday Edge maintenance: {reason}",
            })
            ids.append(str(uuid.UUID(result["silenceID"])))
    except Exception:
        for silence_id in ids:
            try:
                api.request("DELETE", f"/silence/{silence_id}")
            except Exception:
                pass  # The bounded TTL remains the fallback when Grafana is down.
        raise
    return ":".join(ids)


def stop(api, token: str, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    availability_id, restart_id = [str(uuid.UUID(value)) for value in token.split(":")]
    silences = []
    # Validate both before modifying either; never alter another operator's silence.
    for silence_id, window in [(availability_id, "wsl-nightly-availability"), (restart_id, "wsl-nightly-restart")]:
        silence = api.request("GET", f"/silence/{silence_id}")
        actual = sorted(silence["matchers"], key=lambda item: item["name"])
        if silence["createdBy"] != CREATOR or actual != sorted(matchers(window), key=lambda item: item["name"]):
            raise ValueError("Refusing to change a silence not owned by this maintenance helper")
        silences.append(silence)
    restart = silences[1]
    api.request("POST", "/silences", {
        "id": restart_id,
        "matchers": restart["matchers"],
        "startsAt": restart["startsAt"],
        "endsAt": timestamp(now + dt.timedelta(minutes=GRACE_MINUTES)),
        "createdBy": CREATOR,
        "comment": restart["comment"] + " (restart lookback grace)",
    })
    api.request("DELETE", f"/silence/{availability_id}")


def positive_int(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for name in ["start", "run"]:
        command = subparsers.add_parser(name)
        command.add_argument("--ttl-minutes", type=positive_int, default=120)
        command.add_argument("--reason", default="planned deployment or restart")
        if name == "start":
            command.add_argument("targets", nargs="+")
        else:
            command.add_argument("command", nargs=argparse.REMAINDER)
    subparsers.add_parser("stop").add_argument("token")
    args = parser.parse_args()
    if args.action == "start" and not affected(args.targets):
        return 0
    if args.action == "run":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("run requires a command after --")
    api = Grafana()
    if args.action == "stop":
        stop(api, args.token)
        print("Grafana availability maintenance ended; restart grace expires in 35 minutes", file=sys.stderr)
        return 0
    token = start(api, args.ttl_minutes, args.reason)
    print("Created Grafana maintenance for Sunday Edge availability and restarts", file=sys.stderr)
    if args.action == "start":
        print(token)
        return 0

    # Manual lifecycle commands get the same Kuma protection as automated deploys.
    kuma = Path(__file__).with_name("kuma-maintenance.py")
    kuma_id = ""
    try:
        result = subprocess.run(
            [sys.executable, str(kuma), "start", "--ttl-minutes", str(args.ttl_minutes),
             "--reason", args.reason, "sunday-edge", "sunday-edge-analytics",
             "sunday-edge-maintenance", "sunday-edge-research", "sunday-edge-checkpoint-recovery"],
            stdout=subprocess.PIPE, text=True, timeout=120, check=True,
        )
        kuma_id = result.stdout.strip()
        return subprocess.run(command, check=False).returncode
    finally:
        try:
            stop(api, token)
        finally:
            if kuma_id:
                subprocess.run([sys.executable, str(kuma), "stop", kuma_id], timeout=120, check=False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Grafana maintenance failed: {error}", file=sys.stderr)
        raise SystemExit(1)
