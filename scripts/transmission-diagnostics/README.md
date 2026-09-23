# Automatic Transmission stall capture

Windows scheduled task `Transmission stall diagnostics` runs `capture.ps1`
every minute as Rubiss (S4U, highest). It checks the latest Docker health result,
not just the unhealthy state, so one failed probe is sufficient. No capture runs
while the latest check is successful; a short stall can resolve between polls.
The task persists across Windows/WSL/Docker restarts and needs Docker available.
It neither restarts services nor changes RPC/session/media data.

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
response times with UTC Linux samples. Disk response timestamps use the trace's
clock; use its metadata rather than assuming raw durations are milliseconds.
An absent name mapping or a request crossing the trace boundaries is inconclusive.
Check lost buffers and circular overwrite before inferring absence of slow I/O.

This is reactive: short stalls may end before tracing starts, and it cannot
recover events from before the trigger. Tracing adds host work and bounded writes
to E:, so it can perturb latency and should be disabled when investigation ends.
The trace is written directly to E: (not C:); unlike the Linux snapshot it is not
held entirely in memory until completion. A blocked E: path may delay flushing
or prevent a usable trace. The file-size limit does not guarantee write latency.

On failure, at most once per five minutes, a disposable helper joins only
Transmission's PID namespace and takes three proc snapshots one second apart.
It uses the already-installed Transmission image by immutable local image ID,
overrides the entrypoint, has no network, host mounts, Docker socket, writable
root filesystem or persistent state, and is limited to 64 MiB and 16 processes.
All capabilities are dropped except SYS_PTRACE (proc syscall permission) and
DAC_READ_SEARCH (read the daemon owner's descriptor directory). Transmission
itself gains no capabilities and does not need a restart. The collector does not
attach ptrace, read process memory, or capture media contents or credentials.
Kernel stacks may report PermissionError; do not broaden permissions for this.

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
(formatted reports are somewhat larger); typical reports are about 53 KiB.
No C: report files or media copies are created. The diagnostic task does not hold
Transmission locks; Task Scheduler bounds the task to two minutes. Docker CLI calls
have separate timeouts, the collector has a ten-second alarm, and only the named,
ownership-labelled helper can be force-removed after timeout. A failed collection
returns a nonzero task result and does not prevent existing n8n recovery.

Install after PR merge from elevated Windows PowerShell:

```powershell
& E:\Docker\scripts\transmission-diagnostics\capture.ps1 -Install
```

Installation does not restart Docker or Transmission. To test without inducing
an outage, run the same script with `-CaptureNow`; reports mark this as manual.
Check Task Scheduler LastTaskResult and LastRunTime after installation. Inspect
reports locally to verify syscall reads succeeded and `windowsTrace.status` is
`complete`; confirm the collector is stopped with `logman query TransmissionStallIO-v1`.
Stop automatic capture with
`Disable-ScheduledTask -TaskName 'Transmission stall diagnostics'` when the
investigation is complete; retained reports remain on E:.

Tests: `python3 -m unittest discover -s scripts/transmission-diagnostics`.
Windows retention/error tests: `powershell -NoProfile -File
scripts/transmission-diagnostics/test_windows_trace.ps1` (does not start ETW).
Host scripts are installed explicitly, not by the Compose deployment workflow.
