"""Bounded proc-only snapshots; no RPC, ptrace attachment or media reads."""

import json
import os
import platform
from pathlib import Path
import signal
import time


def read(path, limit=2048):
    try:
        with path.open() as stream:
            return stream.read(limit)
    except OSError as error:
        return {"error": type(error).__name__}


def snapshot(proc_root=Path("/proc")):
    for proc in proc_root.glob("[0-9]*"):
        if read(proc / "comm") != "transmission-da\n":
            continue
        threads = []
        try:
            tasks = list((proc / "task").iterdir())[:32]
            descriptors = list((proc / "fd").iterdir())[:512]
        except OSError as error:
            return {"time": time.time(), "error": type(error).__name__}
        for task in tasks:
            threads.append({"tid": int(task.name), "wait": read(task / "wchan"),
                            "syscall": read(task / "syscall"), "stack": read(task / "stack")})
        # Paths stay in local diagnostic reports, never in metrics or alerts.
        fds = {}
        for fd in descriptors:
            try:
                fds[fd.name] = os.readlink(fd)[:512]
            except OSError:
                pass
        return {"time": time.time(), "pid": int(proc.name), "threads": threads, "fds": fds}
    return {"time": time.time(), "error": "daemon_not_found"}


if __name__ == "__main__":
    signal.alarm(10)
    samples = []
    for _ in range(3):
        samples.append(snapshot())
        time.sleep(1)
    print(json.dumps({"architecture": platform.machine(), "samples": samples}))
