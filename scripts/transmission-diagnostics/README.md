# Automatic Transmission stall capture

Windows scheduled task `Transmission stall diagnostics` runs `capture.ps1`
every minute as Rubiss (S4U, highest). It checks the latest Docker health result,
not just the unhealthy state, so one failed probe is sufficient. No capture runs
while the latest check is successful; a short stall can resolve between polls.
The task persists across Windows/WSL/Docker restarts and needs Docker available.
It neither restarts services nor changes RPC/session/media data.

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

Snapshots buffer in helper memory and Windows process memory, then save to
`E:\Scripts\Logs\transmission-stalls\capture-*.json`. Only the newest 20 of these
diagnostic reports are retained. Raw evidence is limited to 1 MiB per capture
(formatted reports are somewhat larger); typical reports are about 53 KiB.
No C: report files or media copies are created. A slow E: write cannot block
Transmission; Task Scheduler bounds the task to two minutes. Docker CLI calls
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
reports locally to verify syscall reads succeeded. Stop automatic capture with
`Disable-ScheduledTask -TaskName 'Transmission stall diagnostics'` when the
investigation is complete; retained reports remain on E:.

Tests: `python3 -m unittest discover -s scripts/transmission-diagnostics`.
Host scripts are installed explicitly, not by the Compose deployment workflow.
