"""Bounded proc snapshots and short, payload-free strace attachment."""

import json
import os
import platform
from pathlib import Path
import signal
import selectors
import shutil
import subprocess
import time

IO_SYSCALLS = ("pread64", "pwrite64", "preadv", "pwritev", "preadv2", "pwritev2", "fsync", "fdatasync")

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
        started = time.time()
        threads = []
        try:
            tasks = list((proc / "task").iterdir())[:32]
            descriptors = list((proc / "fd").iterdir())[:512]
        except OSError as error:
            return {"time": time.time(), "error": type(error).__name__}
        for task in tasks:
            threads.append({"tid": int(task.name), "sampleStarted": time.time(),
                            "wait": read(task / "wchan"), "syscall": read(task / "syscall"),
                            "stack": read(task / "stack"), "schedstat": read(task / "schedstat"),
                            "sampleFinished": time.time()})
        # Paths stay in local diagnostic reports, never in metrics or alerts.
        fds = {}
        for fd in descriptors:
            try:
                fds[fd.name] = os.readlink(fd)[:512]
            except OSError:
                pass
        return {"time": started, "finished": time.time(), "monotonic": time.monotonic(),
                "pid": int(proc.name), "threads": threads, "fds": fds}
    return {"time": time.time(), "error": "daemon_not_found"}


def bounded_command(command, seconds, output_limit=262144):
    """Drain while bounded; SIGINT detaches strace, SIGKILL is the last resort.

    Never use strace --kill-on-exit: stopping the diagnostic must not kill the
    attached daemon. Raw arguments suppress media contents and credential buffers.
    """
    started = time.time()
    deadline = time.monotonic() + seconds
    output = bytearray()
    reason = "exited"
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          start_new_session=True) as process, selectors.DefaultSelector() as events:
        events.register(process.stdout, selectors.EVENT_READ)
        try:
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    reason = "duration_limit"
                    break
                if not events.select(left):
                    continue
                chunk = os.read(process.stdout.fileno(), min(8192, output_limit - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) >= output_limit:
                    reason = "output_limit"
                    break
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.5)
        return {"started": started, "finished": time.time(), "stopReason": reason,
                "exitCode": process.returncode, "text": output.decode("utf-8", errors="replace")}


def trace_io(pid, stacks=False):
    if not shutil.which("strace"):
        return {"status": "unavailable", "error": "strace not installed in diagnostic image"}
    if read(Path(f"/proc/{pid}/comm")) != "transmission-da\n":
        return {"status": "unavailable", "error": "daemon exited before attachment"}
    if attached_threads(pid):
        return {"status": "unavailable", "error": "existing tracer; attachment skipped"}
    command = ["strace", "-qq", "-f", "-ttt", "-T", "-e", "raw=all", "-e", "signal=none",
               "-e", "trace=" + ",".join(IO_SYSCALLS), "-p", str(pid),
               f"--syscall-limit={2 if stacks else 1000}"]
    if stacks:
        command += ["-k", "--stack-trace-frame-limit=16"]
    result = bounded_command(command, 1 if stacks else 2)
    text = result["text"]
    if stacks and "Operation not permitted" in text:
        result["status"] = "unavailable"
        result["error"] = "stack unwinding denied by host permissions"
    elif "ptrace(" in text or "invalid option" in text or "unrecognized option" in text:
        result["status"] = "failed"
    elif any(name + "(" in text for name in IO_SYSCALLS):
        result["status"] = "captured"
    elif result["exitCode"] not in (0, -signal.SIGINT):
        result["status"] = "failed"
    else:
        result["status"] = "no_matching_syscalls"
    return result


def attached_threads(pid):
    attached = []
    for task in Path(f"/proc/{pid}/task").glob("[0-9]*"):
        status = read(task / "status", 4096)
        if isinstance(status, str):
            for line in status.splitlines():
                if line.startswith("TracerPid:") and int(line.split()[1]):
                    attached.append(int(task.name))
    return attached


def collect(trace_enabled=False):
    samples = []
    for _ in range(3):
        samples.append(snapshot())
        time.sleep(1)
    pid = samples[-1].get("pid")
    tracing = {"status": "disabled", "reason": "automatic captures must not attach to the daemon"}
    if trace_enabled and not pid:
        tracing = {"status": "daemon_not_found"}
    if trace_enabled and pid:
        tracing = {"timing": trace_io(pid), "stacks": trace_io(pid, stacks=True)}
        samples.append(snapshot())
        tracing["remainingTracers"] = attached_threads(pid)
    return {"architecture": platform.machine(), "samples": samples, "linuxTrace": tracing}


if __name__ == "__main__":
    # Container cleanup is an independent outer bound if proc/unwinding wedges.
    signal.alarm(15)
    print(json.dumps(collect(trace_enabled=os.environ.get("TRANSMISSION_TRACE_ENABLED") == "1")))
