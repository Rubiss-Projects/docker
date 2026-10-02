Windows health checks must use `127.0.0.1` for the local IPv4 Docker listeners.
After the Windows update, native PowerShell requests to `localhost:32400` and
`localhost:8086` timed out while the same requests to `127.0.0.1` returned 200.
An unsuccessful localhost Plex probe is not evidence that Plex needs a restart.

The installed `E:\Scripts\docker-desktop-common.ps1` now uses IPv4 loopback for
the eight Plex internal/host readiness URLs. Both the watchdog and nightly task
share that source. The prior file and its hash are retained in the maintenance
follow-up journal. Re-enable `Start Docker Desktop if not running` and
`Docker Desktop Nightly Restart` only after the corrected read-only
`Get-ConfirmedDockerHealth` returns `Healthy` and SWAG's persistent login fix is
installed. Do not use a Docker restart as a health-probe test.

Telegraf's existing InfluxDB output now uses `http://127.0.0.1:8086`; all output
credentials, bucket and inputs are retained. `transmission/install-telegraf.ps1`
preserves this setting on future installs. A Telegraf restart briefly interrupts
telemetry collection without restarting applications. Missing observations are
unknown, not successful RPC calls.

The native Windows Tailscale client was logged out (`NeedsLogin`) during the
follow-up, so that client had neither MagicDNS rules nor tailnet DNS information.
Ubuntu's separate active Tailscale endpoint was working. A native Windows
MagicDNS check requires that Windows client to be signed in; it is not a WSL
DNS or VirtioFS validation check. Do not alter Ubuntu's working DNS/MTU setup to
repair the logged-out Windows client.
