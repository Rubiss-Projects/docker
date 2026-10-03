# Windows and WSL memory telemetry

Adds counters to the existing Windows Telegraf -> InfluxDB -> Grafana path.
The **Windows and WSL Memory** dashboard compares host pressure with guest
headroom. No new agent, credentials, network listener or automatic remediation.

| Measurement | Scope and fields |
| --- | --- |
| `win_mem` | Windows resident system cache, committed bytes/commit limit, page inputs/outputs and read/write operations, modified pages; complements existing available/standby/pool counters |
| `wsl_process` | Windows `vmmemWSL*` working set (resident bytes) and private bytes (not all necessarily resident); refreshed process instances support WSL restarts |
| `wsl_memory` | Shared Linux kernel total/available/free/cache/buffers/reclaimable slab, swap use, memory PSI some/full 10/60/300-second averages and cumulative microseconds, collection status |

Windows counters run every 10 seconds. The guest reader runs every 30 seconds
through the existing cAdvisor container, using one fixed `docker exec ... cat`
of `/proc/meminfo` and `/proc/pressure/memory`. It uses the explicit Desktop
Linux engine pipe and does not launch WSL or Docker when stopped. Its Docker CLI
has a four-second wait; an expired read terminates only that owned CLI. Telegraf
has an eight-second outer timeout. Failure emits only `collect_up=0`, never
fabricated zero memory/pressure. No files, torrent metadata or process arguments
are collected. cAdvisor must be running and the Telegraf service account must
have its existing Docker access.

On this WSL backend, cAdvisor and Ubuntu expose the same kernel boot ID, verified
before introduction. These guest counters cover that shared kernel, not a
container limit or a sum of application RSS. Recheck this scope if the Docker
backend changes. The existing Windows `mem` measurement is not Linux headroom.

Interpret the views separately: Windows system cache, WSL working set and Linux
cache are not additive categories. `MemAvailable` estimates reclaimable guest
headroom. Linux `Cached` includes shared-memory pages; it is not all immediately
reclaimable. Page inputs include file-backed reads and alone do not prove swap
thrashing. PSI percentages measure time stalled on memory, not utilization.
Private bytes/commit are different from physical resident memory. Missing samples
remain gaps; the dashboard does not carry a healthy zero across missing data.

## Install after PR review and merge

From elevated Windows PowerShell, run:

```powershell
& 'E:\Docker\scripts\host-memory\install.ps1'
```

The installer preserves unrelated inputs, outputs and credentials; checks the
complete candidate with the installed Telegraf `--test` (no output writes);
requires actual host and guest samples; and saves the original config before
restarting **only Telegraf**. Expect a brief metrics gap, no application outage.
Validation failure leaves the installed config unchanged; restart failure restores
the original bytes and starts Telegraf with them. Backup/candidate config files
inherit the original config's ACL before credential bytes are written.

This directory is not a Compose stack. Host installation is explicit, not part
of the Compose deployment runner. Grafana reads the new provisioned dashboard
on its normal 30-second scan; no Grafana restart is required.

Verify new `win_mem` fields plus `wsl_process` and `wsl_memory` samples in InfluxDB,
`collect_up=1`, and populated dashboard panels. Preserve the existing low-memory
alert thresholds. No WSL memory limit, cache-reclaim or pagefile setting changes.

For backout, copy the exact `.host-memory-backup-...` reported by the installer
over its original config path and restart Telegraf. If an earlier collector
existed, restore the adjacent `.probe.ps1` over `collect-wsl-memory.ps1`; otherwise
the unreferenced collector may be removed. A git revert removes the new dashboard.
Config backups contain existing credentials; do not attach them to a PR or log.

## Focused tests

```powershell
& .\scripts\host-memory\test-collector.ps1
& .\scripts\host-memory\test-install.ps1
```

These exercise parsing, units, locale, malformed/missing samples and managed
config replacement without Docker, Windows counters or service operations.
Native `telegraf --test` additionally validates actual PDH names and field names.

References: [Telegraf Windows counters](https://github.com/influxdata/telegraf/tree/v1.31.3/plugins/inputs/win_perf_counters),
[Linux PSI](https://docs.kernel.org/accounting/psi.html),
[Windows paging interpretation](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/how-to-determine-the-appropriate-page-file-size-for-64-bit-versions-of-windows).
