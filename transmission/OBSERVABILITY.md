# Transmission health and stability

This uses the existing Docker health checks, Homepage, Uptime Kuma, n8n recovery,
Windows Telegraf, InfluxDB, Prometheus/cAdvisor and Grafana. No exporter, daemon,
database, exposed endpoint or second restart controller is added.

## Signals and dashboards

- `scripts/rpc-health.py` negotiates Transmission's HTTP 409 session token and
  validates a successful `session-stats` response. Merely returning 409 is not
  healthy. Docker checks every 30 seconds, allows two minutes for startup and
  requires three failures before marking unhealthy. Each RPC probe has an
  eight-second absolute deadline; Docker additionally has a ten-second timeout.
  LinuxServer's existing custom-init hook copies the probe into the container's
  Linux filesystem at startup, so probe execution does not depend on reading E:.
- Homepage keeps its native Transmission widget and reads functional health
  through its existing Docker integration. Kuma's existing Transmission monitor
  uses its native Docker monitor with Windows Docker host ID 1. It retains its
  existing interval, retries, notifications, maintenance membership and history.
  Installed Kuma **2.5.4** explicitly evaluates `State.Health.Status` in
  `server/model/monitor.js` (healthy → Up, unhealthy → Down, starting → Pending).
  This was checked against its actual running source and all three mocked
  states. The short Docker-monitor list in the older Kuma guidance is not an
  exhaustive description of the current implementation.
- Windows Telegraf executes the same probe every 30 seconds with `--metrics`,
  which adds a lightweight `torrent-get` of only status, error code and peer
  count. Only aggregate metrics are sent to the existing `ben-server` bucket.
  Linux tmpfs locks prevent overlapping probes of each mode. No names, hashes,
  paths, trackers or credentials enter telemetry. RPC is read-only.
- Telegraf's built-in `http_response` input separately checks the published
  Windows port for HTTP 409 and records response time. This preserves endpoint
  reachability visibility across the Windows/Docker boundary, independently of
  the in-container functional check. Endpoint failures alert but do not restart.
- **Transmission Stability** (`/d/transmission-stability`) shows RPC/inventory
  success and latency, torrent state, peer count, payload rates, existing
  cAdvisor memory/CPU/OOM data and observed start-time changes. Current-state
  panels expire samples after 90 seconds; history has gaps, never interpolated
  success. Successful-probe percentage is explicitly not wall-clock uptime.
- The existing **Windows** dashboard (`/d/fdvyllsgg8v7kf`) adds disk latency,
  IOPS and throughput to its repeated Disk row, plus physical-device latency.
  Existing `win_disk` and `win_diskio` measurements receive the new counters.
  Dashboard links preserve the time range for correlating RPC and disk stalls.
- Grafana reports missing telemetry (two-minute query window, two-minute hold),
  slow successful RPC (1.5 seconds for five minutes), and inventory failures
  despite responding session RPC. Existing Kuma/n8n own outage recovery; these
  additional alerts do not restart anything. Notifications use the existing
  Lawson contact point and mute during planned 05:00–05:30 ET host maintenance.
  Missing telemetry and query errors remain distinguishable from daemon health.

The Docker restart alert counts changes of a start-time gauge, grouped by name
and scrape job, rather than incorrectly applying `increase()` to the timestamp.
It includes recreations and can miss multiple starts between 15-second samples;
it is not an exact event counter.

## Apply and verify

1. Deploy the reviewed Compose/scripts/Grafana changes through the normal PR
   path. Pause existing n8n Transmission recovery during planned recreation as
   described in `../n8n/AGENTS.md`, and resume it after functional health returns.
   Future probe-only changes require a planned Transmission restart to refresh
   the Linux copy; an unchanged `compose up` alone does not rerun custom init.
2. Preserve Kuma history before allowing SWAG's label sync to run:
   `docker exec -i swag python3 - < transmission/sync-kuma.py`.
   This edits the existing monitor and updates SWAG's label cache. The mod's
   normal edit path deletes/recreates monitors, so do not use it for this
   migration. Verify monitor 126 still exists and reports `healthy`.
   The installed mod runs as the s6 **oneshot**
   `init-mod-swag-auto-uptime-kuma-install`; its Python entry point synchronizes
   once and disconnects, with no Docker-event subscription. This deployment
   does not change SWAG, Kuma or their dependencies, so it does not rerun that
   init hook. Do not restart SWAG or manually invoke the mod until this step is
   complete. Recheck these assumptions if combining with another deployment.
3. Run `E:\Docker\transmission\install-telegraf.ps1` in elevated PowerShell.
   It backs up the existing configuration, manages only its marked block,
   validates the actual Windows inputs, then restarts Telegraf. The existing
   output and its token are preserved locally and never copied into this repo.
   This host service is outside the Compose deployment runner; rerun the script
   after changing `telegraf.conf`. No-op installs do not restart the service.
4. Grafana dashboards hot-load; reload alert provisioning through the existing
   Grafana admin API (or a planned restart). Verify fresh `transmission`,
   `win_disk` and `win_diskio` samples and evaluate each new alert query.
5. Verify all torrent registrations remain present and both speed-limit flags
   and alternate-speed mode remain disabled. No tuning is part of this change.

Focused tests: `python3 -m unittest discover -s transmission/scripts -p test_rpc_health.py`
and `node --test n8n/scripts/self_heal_container.test.js`. Probe tests cover
session renewal, malformed/incomplete RPC responses, listener-only failures,
timeouts, aggregate inventory and read-only methods.

## Recovery evidence and remaining gaps

Failed functional health probes include bounded Linux thread wait channels,
open descriptor count and cgroup pressure/CPU/memory information. Before a
Transmission restart, the existing n8n helper saves the latest structured health
results, Docker state and one-shot resource statistics. The newest 20 snapshots
live in the n8n container's Linux `/tmp/container-recovery-diagnostics`, and each
snapshot is included in existing n8n execution output/history. This avoids
additional synchronous writes to the suspect E: mount before recovery. Linux
copies do not survive n8n container recreation; execution history is subject to
n8n's normal retention. Capture is best-effort with bounded Docker calls and
does not prevent recovery when diagnostics are unavailable.

Telegraf collection depends on Docker exec. A Docker/WSL outage can prevent collection entirely; this
is reported as missing telemetry, not RPC success. Windows counters continue
independently. A failure of the whole Windows host also takes its local Grafana
and InfluxDB offline. External alert delivery for a total host loss remains a
gap in the current architecture; this phase does not add another observer.

Collect 24–48 hours at uncapped load before choosing a storage/runtime change.
Compare RPC p95/p99 and error periods against E: latency/queue, CPU, memory,
OOM events and captured `p9_client_rpc` waits. The September 22 investigation
observed about 210 MiB RSS for 1,408 torrents, no OOM, and a Windows-backed
storage stall correlation. That does not establish the initial storage stall's
cause or prove capacity at peak load. Do not preemptively reduce torrents,
bandwidth, peer limits or seeding activity. Any storage migration must preserve
the complete session and media/hardlink relationships and have a rollback path.

Protocol reference: https://github.com/transmission/transmission/blob/4.1.3/docs/rpc-spec.md
Telegraf input: https://docs.influxdata.com/telegraf/v1/input-plugins/exec/
