# Caddy Plex remote proxy

Caddy is a **native Ubuntu systemd service**, deliberately outside Docker Desktop
NAT. Plex remains in Docker Desktop. This narrow native-service exception is
necessary to see the incoming public IPv4 peer before forwarding to Plex.

```text
Remote Plex app -> router TCP 18443 -> Ubuntu Caddy -> 127.0.0.1:32400 -> Plex
LAN Plex app -------------------------------------> 192.168.50.40:32400
```

## Public route

- DNS-only `plex-remote.benlawson.dev` CNAME to the existing DNS-only
  `public.benlawson.dev`; the existing Cloudflare DUC maintains its IPv4 address.
  Do not orange-cloud it or put this traffic through Cloudflare Tunnel.
- ASUS static TCP forward: external **18443**, destination **192.168.50.40:18443**.
  Remove only the old public TCP 32400 rule after the new route is verified.
- Plex custom URLs: retain `http://192.168.50.40:32400` and append
  `https://plex-remote.benlawson.dev:18443`. Set `PublishServerOnPlexOnlineKey=0`.
  Preserve other Plex authentication, LAN, relay and bandwidth settings.
- The successful temporary native-iOS test needed the old public rule removed;
  adding a custom URL alone still let the app bypass the proxy. Native playback,
  reduced-quality hardware transcoding, dashboard, Plex WAN classification and
  Tracearr's actual carrier IP worked. Cellular downloads were blocked by the
  app's Wi-Fi policy and remain unverified. LAN discovery is a separate concern.

## Install/update

Use the normal reviewed PR process. Native installation is explicit; Compose
must not create a `caddy` container. For initial onboarding, use a controlled
deployment (`[skip deploy]`) so documentation/monitoring changes do not recreate
Plex or its dependents. The files under `caddy/` are the authoritative sources.

Run `python3 /mnt/e/Docker/caddy/install.py` as root in Ubuntu after merge.
The installer verifies the pinned official Linux amd64 archive against
`release.json`, installs the service/config/helpers and checks HTTPS locally.
`--archive /path/to/caddy.tar.gz` uses the same digest check without downloading.
For configuration changes it reloads Caddy gracefully. It refuses a binary
replacement while Caddy is running: notice a Caddy-only interruption, disable and
stop that unit, then run the installer to enable/start the reviewed new release.
It never stops or recreates Plex/Docker. Protected installation originals live
under `/var/lib/caddy-plex-control/install-*` for operator rollback.
File publication, certificate validation and systemd reload share the helpers'
operational lock. Unique atomic candidates make interrupted writes retryable.

Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
E:\Docker\caddy\install-watchdog.ps1 -Apply` from Windows. The installer holds
the existing Docker operation lock, validates the exact insertion and parser,
preserves access rules and backs up the old watchdog script. It copies only the
DACL onto the empty candidate before writing script bytes, without assigning
the old administrator owner to a new file. Schedules remain unchanged.
If another owner holds the lock, let it finish before installation.

For planned manual stops, create `/run/caddy-plex.maintenance` **before** stopping
the service, and remove it after recovery. Alternatively disable the unit. The
Windows watchdog respects both states and its existing host-maintenance skip.
It invokes a separate Caddy leaf only after successful Docker health/recovery.
Three failed Caddy HTTPS checks permit one Caddy-only restart, with a ten-minute
cooldown; pending transitions and bad configuration are not signalled. Never add
Caddy to the Docker sentinel/daemon failure classification. Systemd also restarts
unexpected process exits with a five-starts-per-five-minutes limit.
If Caddy also hangs during a requested stop, systemd ends only its service after
the 90-second graceful timeout so the replacement can bind its ports. Remote
streams may reconnect; Plex and other services are not part of that stop.

## TLS, permissions and logs

SWAG continues to own wildcard renewal. A root-only oneshot checks the existing
certificate every 15 minutes, validates hostname, dates and matching key, then
atomically switches Caddy's private pair and reloads if changed. The timer retries
failed refreshes; it never overwrites SWAG's originals. A valid pair is required
at boot. Caddy runs as `caddy-plex` with read-only access to the copied pair,
systemd hardening, no root capabilities, and its own Linux state/runtime folders.

The real admin API is a private Unix socket. LAN port **19019** exposes only
GET `/metrics`, GET `/reverse_proxy/upstreams` (Homepage), and GET `/healthz`.
Every other path/method is rejected. Do not forward 19019 on the router.
No trusted upstream proxy is configured: forwarded client addresses are always
replaced with the observed peer. Requests and HTTP error objects are excluded
from logs because Plex tokens can appear in headers and query strings. Do not
enable debug/access logging against real Plex traffic without token redaction.

## Monitoring

- Homepage: official Caddy widget, linked to the Grafana dashboard. Its upstream
  request count is **current in-flight requests**, not lifetime traffic; the
  Grafana request-rate panels provide history.
- Prometheus: `job=caddy`, `instance=ben-server-ubuntu`, 15-second metrics scrape.
- Grafana: upstream **Grafana Labs Caddy Overview**, pinned from
  [grafana/jsonnet-libs](https://github.com/grafana/jsonnet-libs/tree/74c55e5f503a1f84eb939f7c421e366d04f25961/caddy-mixin).
  Original JSON SHA256 `20e99366604f1db4c478efcf27c0d95afab034d9c3d8ce1d8fe72b5fefac11d8`.
  Only local UID, null database ID, default data source and 30-second refresh
  differ. Its Apache-2.0 license is retained in `GRAFANA-LICENSE`.
- Provisioned Grafana alerts cover missing metrics, failed Plex upstream and
  repeated HTTP 5xx. Existing Discord routing and 05:00–05:30 host-maintenance
  mute apply. Streaming requests are naturally long; no generic latency alarm.
- Run `python3 /mnt/e/Docker/caddy/sync-monitor.py` once routing is ready. It adds
  the manual `caddy` Kuma TLS/identity monitor under Infrastructure using the
  existing Plex Discord notification assignments. Its Docker self-heal webhook
  is excluded: Caddy recovery belongs to the native watchdog. TLS validation and
  expiry alerts stay enabled. No new credentials or notification channel is created.
- Hot-reload Prometheus configuration and Grafana alerting provisioning, and
  let the dashboard file provider/Homepage observe changed files. Verify actual
  scrapes, all three rules, the widget and fresh Kuma heartbeats after rollout.

## Backout

Save exact current router/Plex settings privately before activation. If remote
checks fail, first restore the original public TCP 32400 forwarding rule and
original Plex custom URLs/public-endpoint setting, verifying discovery/access.
Then remove only the new 18443 rule and owned DNS alias. Preserve other rules.
Disable Caddy (or set its hold) before stopping it. Remove/disable its owned Kuma
monitor and revert monitoring configuration via PR. Restore the exact saved
watchdog script under its operation lock if removing the hook. A failed Caddy
installation never authorizes a Docker, WSL, Windows or network-service restart.

## Focused validation

`CADDY_BINARY=/path/to/pinned/caddy python3 -m unittest discover -s caddy -p 'test_*.py'`
runs the actual Caddyfile against a loopback fake Plex and synthetic TLS. It
checks source-header replacement, Plex authentication propagation, byte ranges,
WebSocket upgrades, TLS/Host matching, read-only monitoring, and watchdog
maintenance/transient/cooldown behavior. These tests do not contact production.
