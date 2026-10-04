# Caddy Plex remote and Channels LAN proxy

Caddy is a **native Ubuntu systemd service**, deliberately outside Docker Desktop
NAT. Plex remains in Docker Desktop. This narrow native-service exception is
necessary to see the incoming public IPv4 peer before forwarding to Plex.

```text
Remote Plex app -> router TCP 18443 -> Ubuntu Caddy -> 127.0.0.1:32400 -> Plex
LAN Plex app -------------------------------------> 192.168.50.40:32400
LAN Channels app -> Caddy :18089 -> existing SWAG :443 -> channels-dvr:8089
```

## Channels At Home

Use **192.168.50.40:18089** in the Channels app's **Connect At Home** screen.
The Apple TV trial played both IPTV and HDHomeRun TV; recording byte ranges
and seeking transport also passed. Automatic mDNS discovery is separate and
unchanged. The ordinary 8089/remote-auth route remains available and unchanged.

No extra relay container is needed. Native Caddy accepts media requests only
from the actual TCP peer in `192.168.50.0/24` with Host `192.168.50.40`, then uses
verified HTTPS to the existing SWAG container on localhost:443. SWAG's exact
`channels-lan-relay.benlawson.dev` virtual host requires a private 256-bit key
on every request and forwards over `proxynet`. There is **no DNS alias or router
forward** for this route or port 18089. The key is still essential: callers can
select any SWAG virtual host through its existing public 443 endpoint.

Both proxies strip supplied client-address/auth-bypass headers. SWAG removes
the private key before contacting Channels and uses an ordinary internal request;
it never sets `X-DVR-SkipAuth` or relaxes Channels' global authentication. Real
LAN peers get the normal trusted-home access, including application write methods.
Do not widen the peer matcher to all private networks or trust X-Forwarded-For.

The shared key lives only in git-crypt's `caddy/channels-lan.env.secret` source
and protected generated configuration. `install.py` validates its format,
renders `/etc/caddy-plex/channels-lan.caddy` and SWAG's ignored
`config/nginx/channels-lan-private/key.conf`, validates both servers, reloads
SWAG, then reloads Caddy. Missing SWAG key material denies all relay requests;
the installer refuses extra key includes. Never print the rendered configuration
or use `nginx -T` against it. No access/error request logging is enabled here.

Kuma checks the harmless GET `/healthz` on the LAN listener (private peers may
read only that endpoint); the native watchdog checks both Caddy listeners. Caddy
active health checks verify the keyed SWAG -> Channels `/status` route. Grafana
alerts on that upstream failing or repeated Channels 5xx; the existing official
Caddy dashboard/widget covers both proxies. An upstream failure does **not**
restart healthy Caddy, Docker, SWAG or Channels.

For a config-only rollout, use `[skip deploy]`, run the installer explicitly,
sync the monitors and reload Grafana alert provisioning. No Compose recreation is
needed. If an expiring trial still owns 18089, stop only its recorded user unit
before the native reload; its owner removes only its temporary relay. Existing
Channels streams through that trial may need reconnecting. Test the permanent
route from a real LAN host and verify the private SWAG vhost refuses missing,
wrong and spoofed keys. Public Plex and the original Channels route must retain
their behavior. Both nginx and Caddy reload gracefully; long connections may
reconnect and must not be treated as authorization to restart applications.

To back out only Channels, restore the saved native Caddyfile, health helper and
Channels include under the Caddy operation lock, validate and reload Caddy.
Remove the owned SWAG relay vhost/key (or revert via PR), run `nginx -t` and reload.
Disable the owned `caddy-channels-lan` monitor and revert its Grafana rules/link.
Do not revert Plex, router settings, Channels data or any Docker container.

## Public route

- DNS-only `plex-remote.benlawson.dev` CNAME to the existing DNS-only
  `public.benlawson.dev`; the existing Cloudflare DUC maintains its IPv4 address.
  Do not orange-cloud it or put this traffic through Cloudflare Tunnel.
- ASUS static TCP forward: external **18443**, destination **192.168.50.40:18443**.
  Keep the old route until the new one passes an outside-network TLS check.
  Then remove the Plex 32400 entries from **both WAN port forwarding and Open
  NAT**: the latter also has a `Plex Media Server@PC` TCP/UDP profile. Preserve
  unrelated rules and verify public 32400 is closed while LAN 32400 still works.
- Plex custom URLs: retain `http://192.168.50.40:32400` and append
  `https://plex-remote.benlawson.dev:18443`. Set `PublishServerOnPlexOnlineKey=0`.
  Preserve other Plex authentication, LAN, relay and bandwidth settings.
- The successful temporary native-iOS test needed the old public rule removed;
  adding a custom URL alone still let the app bypass the proxy. Native playback,
  reduced-quality hardware transcoding, dashboard, Plex WAN classification and
  Tracearr's actual carrier IP worked. Cellular downloads were blocked by the
  app's Wi-Fi policy and remain unverified. LAN discovery is a separate concern.

An ASUS Apply success/configuration readback does not prove forwarding is active.
Check the router's active forwarding table and the public endpoint. During this
rollout, a stuck `restart_letsencrypt` service request caused the router to save
settings but skip firewall reloads and even the normal reboot request. If that
recurs, stop cutover, restore saved routing and verify recovery before continuing;
do not repeat Apply or infer a reboot from brief HTTP unavailability. The router's
ASUS DDNS/OpenVPN/certificate features are separate from SWAG's wildcard renewal
used by Caddy.

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
It reloads the private SWAG hop but never stops or recreates containers. Protected installation originals live
under `/var/lib/caddy-plex-control/install-*` for operator rollback.
File publication, certificate validation and systemd reload share the helpers'
operational lock. Unique atomic candidates make interrupted writes retryable.

Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
E:\Docker\caddy\install-watchdog.ps1 -Apply` from Windows. The installer holds
the existing Docker operation lock, validates the exact insertion and parser,
preserves access rules/owner and backs up the old watchdog script. It copies the
DACL and verifies ownership before writing script bytes. Run from a normally
elevated PowerShell session when preserving administrator ownership requires it;
an unelevated refusal leaves the watchdog unchanged. If Windows partially moves
files during replacement, the installer retains the candidate and original backup
for recovery rather than deleting the remaining replacement. Schedules remain unchanged.
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
- Validate Prometheus with `docker exec prometheus promtool check config /etc/prometheus/prometheus.yml`, then hot-reload using `docker exec prometheus /bin/sh -c 'kill -HUP 1'` (not Docker's kill API; see `../prometheus/AGENTS.md`). Reload Grafana alerting provisioning, and
  let the dashboard file provider/Homepage observe changed files. Verify actual
  scrapes, all three rules, the widget and fresh Kuma heartbeats after rollout.

## Backout

Save exact current WAN forwarding, Open NAT and Plex settings privately before
activation. If remote checks fail, first restore the saved Plex 32400 entries in
both router lists and original Plex custom URLs/public-endpoint setting, verifying
active forwarding and discovery/access. Do not overwrite unrelated concurrent edits.
Then remove only the new 18443 rule and owned DNS alias. Preserve other rules.
Disable Caddy (or set its hold) before stopping it. Remove/disable its owned Kuma
monitor and revert monitoring configuration via PR. Restore the exact saved
watchdog script under its operation lock if removing the hook. A failed Caddy
installation never authorizes a Docker, WSL, Windows or network-service restart.

## Focused validation

`CADDY_BINARY=/path/to/pinned/caddy python3 -m unittest discover -s caddy -p 'test_*.py'`
also requires `NGINX_TEST_IMAGE` set to the installed SWAG image ID (no pull).
It runs the actual Caddyfile against a loopback fake Plex and synthetic TLS. It
checks source-header replacement, Plex authentication propagation, byte ranges,
WebSocket upgrades, TLS/Host matching, read-only monitoring, and watchdog
maintenance/transient/cooldown behavior. The Channels tests use one disposable
nginx container with synthetic TLS/backend/key, no production mounts and a
loopback-only port; both owned processes are stopped and the fixture removed.
They exercise the actual Caddy/SWAG route, peer/Host/key rejection, forwarding
header stripping, app methods, ranges and WebSockets. They do not contact production.
