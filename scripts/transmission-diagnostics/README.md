# Automatic Transmission stall capture

Windows scheduled task `Transmission stall diagnostics` runs `capture.ps1`
every minute as Rubiss (S4U, highest). It checks the latest Docker health result,
not just the unhealthy state, so one failed probe is sufficient. No capture runs
while the latest check is successful; a short stall can resolve between polls.
The task persists across Windows/WSL/Docker restarts and needs Docker available.
It neither restarts services nor changes RPC/session/media data.

**September 24 incident correction:** automatic captures are passive again.
Two downloads reported `Interrupted system call` around ptrace captures; causation
is unproven, but attachment can interrupt syscalls and is unsuitable for unattended
capture on this host. The filesystem stall predates attachment. Proc snapshots,
scheduling counters, clock calibration and Windows ETW remain enabled. Neither
scheduled runs nor plain `-CaptureNow` attach strace, even if its helper is installed.

## Correlated Windows I/O trace

On the same trigger, the task starts a 20-second Windows ETW trace immediately
before collecting Linux snapshots. It uses the built-in `logman`/Performance
Logs and Alerts (PLA) collector, not a new service or a continuous recorder.
`Microsoft-Windows-Kernel-File` records file names, read/write starts and operation
ends; `Microsoft-Windows-Kernel-Disk` records disk operations and response times.
No media payloads, process command lines, stacks or network payloads are enabled.
ETW does include host-wide private file paths and process IDs: keep it local.

The reserved collector `TransmissionStallIO-v1` has its own PLA-managed duration
limit, which stops tracing even if the invoking PowerShell process dies. Do not
use that collector name for other work. It does not stop WPR or other ETW sessions.
The global capture mutex serializes runs; the next capture replaces any leftover
collector definition. Existing five-minute capture cooldown still applies.

Each circular ETL is capped at 64 MiB; only the newest five `io-<timestamp>_*.etl`
files are retained (up to 320 MiB). Reports link the ETL to Linux samples and
include UTC start/end times, QPC frequency, process ID/name mappings and lost
buffer counts. Windows appends a sequence number to the trace filename.
Windows-trace failures are recorded in JSON and return a failed task result,
but do not suppress Linux evidence or the separate n8n recovery controller.

Analyze ETLs offline using Windows Performance Analyzer, or Windows' existing
`Get-WinEvent -Path <etl> -Oldest` / `tracerpt`. Match file read starts and operation
ends by IRP, associate file objects with file-name events, and compare disk
response times with calibrated Linux samples. Disk response timestamps use the trace's
clock; use its metadata rather than assuming raw durations are milliseconds.
An absent name mapping or a request crossing the trace boundaries is inconclusive.
Check lost buffers and circular overwrite before inferring absence of slow I/O.

This is reactive: short stalls may end before tracing starts, and it cannot
recover events from before the trigger. Tracing adds host work and bounded writes
to E:, so it can perturb latency and should be disabled when investigation ends.
The trace is written directly to E: (not C:); unlike the Linux snapshot it is not
held entirely in memory until completion. A blocked E: path may delay flushing
or prevent a usable trace. The file-size limit does not guarantee write latency.

## Linux timing and clock calibration

Before and after each capture, three guest time readings are bracketed by Windows
UTC and measured with a monotonic stopwatch. Reports contain the interval for
**Linux minus Windows**, raw samples and round-trip time. Subtract that interval
from Linux timestamps to compare them with ETW; preserve the uncertainty rather
than claiming an exact midpoint. Wall-clock jumps, failed samples or inconsistent
intervals are marked uncertain/unavailable. Compare the before/after intervals;
disjoint intervals produce `offset_changed`. Even `consistent_endpoints` cannot
exclude an intervening clock step. Do not extrapolate this calibration to older
incidents or across clock changes, or infer exact cross-host timing during drift.

On failure, at most once per five minutes, a disposable helper joins only
Transmission's PID namespace and takes three proc snapshots one second apart.
It uses the existing Transmission image by immutable ID. Only an explicitly
requested manual trace adds syscall tracing and a fourth snapshot, using a built
local diagnostic image (pinned Transmission base plus strace) by immutable ID,
overrides the entrypoint, has no network, host mounts, Docker socket, writable
root filesystem or persistent state, and is limited to 128 MiB and 16 processes.
All capabilities are dropped except SYS_PTRACE (proc reads and short attachment) and
DAC_READ_SEARCH (read the daemon owner's descriptor directory). Transmission
itself gains no capabilities and does not need a restart.

Manual tracing requires `-CaptureNow -EnableLinuxTracing`; do not enable it in the
scheduled task. Before using it, account for its potential to interrupt writes and
stop downloads. Healthy-run detach tests do not rule out this effect during stalls.
Strace attaches for at most two seconds/1,000 selected calls, recording raw
arguments and durations for positioned reads/writes (including preadv2/pwritev2),
fsync and fdatasync. A separate
one-second/two-call pass attempts user-space unwinding (up to 16 frames); this
can read process memory for unwinding but does not output media/credential
buffers. Both passes cap output at 256 KiB. SIGINT detaches, with SIGKILL of the
tracer as fallback; never use strace's kill-on-exit option. Existing tracers cause
attachment to be skipped. The report checks for remaining attached threads.

On this Docker Desktop host user-stack unwinding currently reports Operation not
permitted; this is recorded as unavailable, not a successful stack capture. Kernel
stacks may also report PermissionError. Do not broaden privileges to bypass this.
Timing works independently. Raw schedstat values (CPU time, run-queue wait in ns,
timeslices) and per-thread sample bounds help separate scheduling from I/O waits;
counters can be disabled or unavailable on some kernels. Tracing adds scheduling
stops and affects measured latency; these are instrumented durations, not a clean
performance benchmark. A hot process can reach the call limit before two seconds.

Automatic captures report `linuxTrace.status=disabled` as a successful passive mode.
For manual tracing, if the helper identity file is absent, proc collection falls
back to the runtime image and saves a partial report with tracing unavailable and
a failed task result.
An unavailable optional stack does not fail otherwise successful timing capture.

Evidence contains architecture, raw syscall number/arguments, thread wait
channels, descriptor-to-path mappings, timestamps and recent Docker health
history. Decode syscall numbers for the recorded architecture. Descriptor-based
operations can be mapped to files; pathname-pointer calls and short-lived races
may need further tracing. This is evidence collection, not a guaranteed root
cause determination. Local reports contain private file paths, so do not publish
them or send their contents to metrics/Discord.

Linux snapshots buffer in helper memory and Windows process memory, then save to
`E:\Scripts\Logs\transmission-stalls\capture-*.json`. Only the newest 20 of these
diagnostic reports are retained. Raw evidence is limited to 1 MiB per capture
(formatted reports are somewhat larger).
No C: report files or media copies are created. The diagnostic task does not hold
Transmission locks; Task Scheduler bounds the task to two minutes. Docker CLI calls
have separate timeouts, the collector has a fifteen-second alarm, and only the named,
ownership-labelled helper can be force-removed after timeout. A failed collection
returns a nonzero task result and does not prevent existing n8n recovery.

Install after PR merge from elevated Windows PowerShell:

```powershell
& E:\Docker\scripts\transmission-diagnostics\capture.ps1 -Install
```

Only for a separately planned manual trace, `install-linux-helper.ps1` builds its
helper. This explicit build needs network access to the image registry/package repository;
capture never builds or pulls. Rebuild after changing the diagnostic Dockerfile.
Installation does not restart Docker or Transmission. To test without inducing
an outage, run the same script with `-CaptureNow`; reports mark this as manual.
Check Task Scheduler LastTaskResult and LastRunTime after installation. Inspect
reports locally to verify syscall reads succeeded and `windowsTrace.status` is
`complete`, linuxTrace is disabled for passive captures (for manual tracing,
timing is captured/no_matching_syscalls and remainingTracers is empty), and
clockCalibration contains usable bounds; confirm the collector is stopped with
`logman query TransmissionStallIO-v1`.
Stop automatic capture with
`Disable-ScheduledTask -TaskName 'Transmission stall diagnostics'` when the
investigation is complete; retained reports remain on E:.

Tests: `python3 -m unittest discover -s scripts/transmission-diagnostics`.
Windows retention/error tests: `powershell -NoProfile -File
scripts/transmission-diagnostics/test_windows_trace.ps1` (does not start ETW).
Clock tests: run `test_clock_calibration.ps1` in Windows PowerShell.
Host scripts are installed explicitly, not by the Compose deployment workflow.
