# Plex Media Server

Plex runs on native BEN-SERVER at `192.168.50.40` with host networking and the
installed NVIDIA runtime. Follow the root deployment guidance and
`../scripts/native-media-network/README.md`. The native adapter applies the
accepted host overrides to the repository's Compose source defaults; do not run
the unadapted Compose file or add WSL driver mounts to the native recipe.

## Deployment and state

Use `python3 -B scripts/native-deploy/compose.py --stack plex -- ...` from
`/srv/Docker`. Preserve the admitted `/config` volume, read-only NAS media mapping,
GPU reservation, `/transcode` tmpfs, resource limits and existing Plex identity.
Never initialize an empty config directory or claim this server again as a
routine repair. The verified NAS mount and media INPUT guard are prerequisites.

Keep `VERSION=docker` and the numeric image version plus digest pin. During image
upgrades, `/identity` can return HTTP 503 while Plex migrates, analyzes or vacuums
its databases. The deploy helper allows 30 minutes for readiness. Inspect the
server log before acting; a slow migration alone does not justify restarting it.

## Accepted networking

- LAN: direct native TCP 32400, with Plex's certificate-backed `plex.direct`
  endpoint for secure clients.
- Remote: the existing public TCP 18443 mapping goes to BEN-SERVER TCP 32400.
  Plex publishes its manual external port and secure direct endpoint.
- Caddy and its custom remote URL are retired. Do not reinstall its service,
  certificate timer or temporary LAN relay. SWAG is not Plex's media proxy.
- Preserve the accepted authentication, TLS, Relay, bandwidth and LAN-classification
  settings. Do not classify WAN clients as LAN or trust arbitrary forwarding headers.
- Homepage opens `https://app.plex.tv/desktop/`; internal consumers use the
  accepted `plex` host alias on port 32400. Preserve these aliases when deploying
  Homepage, Tracearr and other consumers.

Normal LAN Plex playback and remote playback/seeking with unchanged quality were
accepted by the owner after migration. The forced 1080p-to-720p transcoding test
was waived; do not describe that specific test as passed.

## Operation and troubleshooting

Inspect `/identity`, current sessions and the Plex server log before lifecycle
changes. Check actual container mounts and the NAS guard when media is missing.
Use existing library paths and metadata; do not remove libraries or rescan the
entire catalog as a generic connectivity fix.

For GPU issues, check `docker exec plex nvidia-smi`, native runtime visibility,
Plex Pass and the existing hardware-transcoding setting. Do not use Windows
driver mounts or change playback quality without a relevant test request.

For remote issues, check native TCP 32400 readiness, the existing router TCP
18443 mapping, DNS and Plex's published secure endpoint. Compare a normal client
on cellular with LAN access. Diagnose the failing route without restarting
unrelated applications or restoring the retired proxy.

Tracearr uses the accepted internal Plex endpoint and an encrypted token. Keep
the existing Plex/Tracearr user association and session history. Sonarr/Radarr
connections also retain their accepted host alias and token. Do not log tokens,
claim codes, preferences containing credentials or authenticated request URLs.

Use the existing Grafana dashboards and alert channels. Repository monitoring
changes must remain provisioned as code. New recurring backup infrastructure is
outside this migration; preserve existing recovery archives and owner decisions.

Any rollback must reconcile current application writes, storage and routing
before activating a single owner. Historical Caddy and Windows definitions are
available in Git history; their removal does not authorize source-disk erasure.
