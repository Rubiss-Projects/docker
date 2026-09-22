#!/usr/bin/env python3
"""Read-only RPC health and aggregate Telegraf metrics; never change session state."""

import argparse
import base64
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import urllib.error
import urllib.request

MAX_RESPONSE = 4 * 1024 * 1024


class ProbeError(Exception):
    pass


class RPC:
    def __init__(self, url, timeout=3):
        self.url = url
        self.timeout = timeout
        self.session = ""
        self.listener_up = False
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method, arguments=None):
        headers = {"Content-Type": "application/json"}
        if os.environ.get("USER") and os.environ.get("PASS"):
            credentials = f'{os.environ["USER"]}:{os.environ["PASS"]}'.encode()
            headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode()
        for _ in range(2):
            headers["X-Transmission-Session-Id"] = self.session
            request = urllib.request.Request(self.url, json.dumps({
                "method": method, "arguments": arguments or {},
            }).encode(), headers)
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    self.listener_up = True
                    body = response.read(MAX_RESPONSE + 1)
                if len(body) > MAX_RESPONSE:
                    raise ProbeError("response_too_large")
                result = json.loads(body)
                if result.get("result") != "success" or not isinstance(result.get("arguments"), dict):
                    raise ProbeError("invalid_rpc_result")
                return result["arguments"]
            except urllib.error.HTTPError as error:
                self.listener_up = True
                self.session = error.headers.get("X-Transmission-Session-Id", "")
                error.close()
                if error.code != 409 or not self.session:
                    raise ProbeError(f"http_{error.code}") from None
        raise ProbeError("session_negotiation_failed")


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ProbeError("invalid_numeric_field")
    return value


def collect(rpc, inventory=False):
    started = time.monotonic()
    result = {"rpc_up": 0, "listener_up": 0, "inventory_up": 0}
    try:
        stats = rpc.call("session-stats")
        values = {target: number(stats[source]) for source, target in {
            "torrentCount": "torrents", "activeTorrentCount": "active_torrents",
            "pausedTorrentCount": "paused_torrents", "downloadSpeed": "download_bytes_per_second",
            "uploadSpeed": "upload_bytes_per_second",
        }.items()}
        result.update(values, rpc_up=1, rpc_seconds=time.monotonic() - started)
        if inventory:
            inventory_start = time.monotonic()
            torrents = rpc.call("torrent-get", {"fields": ["status", "error", "peersConnected"]})["torrents"]
            if not isinstance(torrents, list):
                raise ProbeError("invalid_inventory")
            states = {state: 0 for state in range(7)}
            errors = peers = 0
            for torrent in torrents:
                state = number(torrent["status"])
                if state not in states:
                    raise ProbeError("invalid_torrent_status")
                states[state] += 1
                errors += int(number(torrent["error"]) > 0)
                peers += number(torrent["peersConnected"])
            result.update(inventory_up=1, inventory_seconds=time.monotonic() - inventory_start,
                          downloading=states[4], seeding=states[6], checking=states[1] + states[2],
                          queued=states[3] + states[5], torrent_errors=errors, peers=peers)
    except Exception as error:
        # Error strings, torrent names, tracker URLs and credentials never enter telemetry.
        result["error"] = str(error) if isinstance(error, ProbeError) else type(error).__name__
    result.update(listener_up=int(rpc.listener_up), probe_seconds=time.monotonic() - started,
                  observed_at=int(time.time()))
    if "rpc_seconds" not in result:
        result["rpc_seconds"] = result["probe_seconds"]
    return result


def diagnostics():
    """Bounded Linux-only evidence, without reading media or revealing paths/trackers."""
    result = {}
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if proc.joinpath("comm").read_text().strip() != "transmission-da":
                continue
            result["pid"] = int(proc.name)
            result["threads"] = [{"tid": int(task.name), "wait": task.joinpath("wchan").read_text().strip()[:80]}
                                 for task in list(proc.joinpath("task").iterdir())[:32]]
            result["open_fds"] = len(list(proc.joinpath("fd").iterdir()))
            break
        except OSError:
            continue
    for name in ("memory.current", "memory.events", "io.pressure", "cpu.stat"):
        try:
            result[name] = Path("/sys/fs/cgroup", name).read_text()[:1024]
        except OSError:
            pass
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", action="store_true")
    args = parser.parse_args()
    mode = "metrics" if args.metrics else "health"
    # Linux tmpfs locks keep a stuck prior invocation from accumulating RPC requests.
    with open(f"/tmp/transmission-{mode}.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("probe_already_running", file=sys.stderr)
            return 1
        def deadline(_signal, _frame):
            raise ProbeError("deadline_exceeded")
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(8)
        result = collect(RPC("http://127.0.0.1:9091/transmission/rpc"), args.metrics)
        signal.alarm(0)
        if args.metrics:
            fields = ",".join(f"{key}={value}" for key, value in result.items() if key != "error")
            print(f"transmission,service=transmission {fields}")
            return 0  # Failed RPC is a measured zero; collector failure produces no sample.
        if not result["rpc_up"]:
            result["diagnostics"] = diagnostics()
        print(json.dumps(result, separators=(",", ":")))
        return 0 if result["rpc_up"] else 1


if __name__ == "__main__":
    sys.exit(main())
