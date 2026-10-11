# Image updates

## Policy

Use `publisher/image:tag@sha256:digest` for every Compose image and Dockerfile base.
The tag tells Dependabot which release or supported channel to follow; the digest
fixes the exact content Docker runs. A digest prevents a changed tag from silently
changing a deployment. It does not certify that a newly published image is safe.

Prefer comparable stable version tags. For LinuxServer use its three-part numeric
aliases, such as `sonarr:4.0.20`, not `version-4.0.20.3014`. Dependabot's stable-tag
heuristic compares against `latest`; four-part aliases can be misclassified as
prereleases, while tags containing build hashes or distro revisions may only get
digest refreshes for the old release.

Use publisher-supported channels where numeric tags do not work reliably:
`uptime-kuma:2`, `timescaledb-ha:pg18`, PostgreSQL `14`, Redis `8-alpine`, and the
existing Java-specific Minecraft channels. Always include the digest. Database
major and Java runtime changes need deliberate compatibility/migration review.
Timescale extension migrations are performed by the deployment helper after a
database backup; updating its container alone leaves installed SQL extensions old.
The workflow loads that helper from the trusted deployment commit before the
helper updates the canonical checkout, including on its first deployment.

Dependabot checks run each Saturday, staggered from 06:00 through 10:10
America/Chicago. Both Dockerfiles have `docker` entries; Compose-only checks do not
inspect their `FROM` lines. Private Sunday Edge images retain the configured GHCR
registry credentials. n8n uses the publisher's direct Docker Hub repository after
repeated HTTP 429 failures through docker.n8n.io. Staggering reduces request bursts
but cannot eliminate registry quotas; investigate failed or missing weekly jobs.

PR validation runs `python3 scripts/check_image_pins.py` to enforce pins, stable
LinuxServer aliases, and weekly coverage. Existing Dependabot queue rules still
require passing PR checks and the previous deployment, and hold major version
changes for review. Weekly checks do not guarantee that every PR deploys that day.
New app releases after a check, publisher image build delays, and beta release
notifications can legitimately appear before the next stable image update.

Native Caddy is governed by `caddy/release.json`, outside Docker Dependabot. Game
server downloads and Homebridge plugins installed inside containers are also
separate from the container image; image digest protection does not cover them.

## Audit: 2026-10-11

Audited all 50 Compose stacks (59 image references and one build-only service),
both tracked Dockerfiles, registry manifests/tags, recent Dependabot job logs,
the merge/deployment queue, and live main-host/Pi containers. All resulting
container references and both base images are digest-pinned. The table records
the selected stable release/channel at audit time, not a permanently current list.

Confirmed stalled upgrades: Plex, Sonarr, Radarr, Prowlarr, Socket Proxy, Uptime
Kuma, n8n, and Tracearr's compound Timescale image tag. LinuxServer aliases are
normalized consistently across the remaining services. SWAG's failed digest
refresh hit HTTP 429. Homepage's newer release arrived after the Saturday check.
Portainer was behind the registry; its selected numeric tag itself is compatible.
The Astroneer and diagnostic Dockerfile bases lacked Dockerfile update coverage.
Other changes below add missing digests or catch up rebuilds in existing channels.

| Stack | Selected image tag(s) | Audit outcome |
| --- | --- | --- |
| `ai-assistant` | `ai-assistant:v1.26.0` | Add digest; retain current stable release |
| `ark-ascended` | `ark-ascended-server:v1.5.2` | Add digest; retain current stable release |
| `ark` | `ark-server:latest-1791186293` | Add digest; retain current stable release |
| `astroneer` | `steamcmd:root (Dockerfile)` | Pin steamcmd base and replace ineffective Compose job with Docker job |
| `audiobookshelf` | `audiobookshelf:2.37.1` | Add digest; retain current stable release |
| `autobrr` | `autobrr:v1.88.0` | Add digest; retain current stable release |
| `bazarr` | `bazarr:1.6.2` | Normalize LinuxServer alias; same release/digest |
| `bitwarden` | `lite:latest`, `postgres:14` | Refresh PostgreSQL 14 digest; retain database major |
| `bookshelf-audio` | `bookshelf:hardcover` | Current stable release/channel; retain pin |
| `bookshelf` | `bookshelf:hardcover` | Current stable release/channel; retain pin |
| `cadvisor` | `cadvisor:v0.55.1` | Add digest; retain current stable release |
| `calibre` | `calibre:9.16.0` | Normalize LinuxServer alias; same release/digest |
| `channels-dvr` | `channels-dvr:nvidia` | Current stable release/channel; retain pin |
| `cloudflare-duc` | `cloudflare-duc-go:latest` | Current stable release/channel; retain pin |
| `cloudflare-tunnel` | `cloudflared:2026.10.0` | Add digest; retain current stable release |
| `cross-seed` | `cross-seed:6.13.7` | Current stable release/channel; retain pin |
| `grafana` | `grafana:13.2` | Current stable release/channel; retain pin |
| `homepage` | `homepage:v2.5.0` | Catch up release published after weekly check; add digest |
| `influxdb` | `influxdb:2.9.1` | Add digest; retain current stable release |
| `it-tools` | `it-tools:latest` | Current stable release/channel; retain pin |
| `lazywarden` | `lazywarden:latest` | Current stable release/channel; retain pin |
| `minecraft` | `minecraft-server:java25` | Refresh Java 25 channel digest |
| `mod-mc` | `minecraft-server:java17` | Refresh Java 17 channel digest |
| `n8n` | `n8n:2.42.6` | Catch up after failed checks; use direct publisher registry and add digest |
| `nvidia-smi-rest` | `nvidia-smi-rest:latest` | Current stable release/channel; retain pin |
| `palworld` | `palworld-dedicated-server:latest` | Current stable release/channel; retain pin |
| `pi/cadvisor` | `cadvisor:v0.55.1` | Add digest; reconcile live latest tag to repository v0.55.1 |
| `pi/cloudflare-tunnel` | `cloudflared:2026.10.0` | Add digest; retain current stable release |
| `pi/glances` | `glances:latest-full` | Refresh full-image channel digest |
| `pi/homebridge` | `homebridge:2026-09-25` | Add digest; retain current stable release |
| `pi/node-exporter` | `node-exporter:v1.12.1` | Add digest; retain current stable release |
| `pi/pi-hole` | `pihole:2026.09.0` | Add digest; retain current stable release |
| `pi/speedtest-tracker` | `speedtest-tracker:1.15.0` | Normalize alias and refresh digest |
| `plex` | `plex:1.43.4` | Fix hashed version alias; catch up to stable |
| `portainer` | `portainer-ce:2.45.2` | Catch up stable release; add digest |
| `prometheus` | `prometheus:v3.15.0` | Current stable release/channel; retain pin |
| `prowlarr` | `prowlarr:2.6.5` | Fix four-part alias; catch up to stable |
| `radarr` | `radarr:6.4.4` | Fix four-part alias; catch up to stable |
| `recyclarr` | `recyclarr:8.7.3` | Add digest; retain current stable release |
| `seerr` | `seerr:book-support` | Current stable release/channel; retain pin |
| `socket-proxy` | `socket-proxy:3.4.6` | Fix distro-revision alias; catch up to stable |
| `sonarr` | `sonarr:4.0.20` | Fix four-part alias; catch up to stable |
| `speedtesttracker` | `speedtest-tracker:1.15.0` | Normalize alias and refresh digest |
| `sunday-edge` | `sunday-edge-analytics:v0.2.45`, `sunday-edge-compute:v0.2.45`, `sunday-edge-maintenance:v0.2.45`, `sunday-edge-research:v0.2.45`, `sunday-edge-watchdog:v0.2.45` | Add digest; retain current stable release |
| `swag` | `swag:5.8.0` | Normalize alias; catch up digest after rate-limited check |
| `tracearr` | `redis:8-alpine`, `timescaledb-ha:pg18`, `tracearr:2.7.1` | Keep app/Redis; advance Timescale within PostgreSQL 18 |
| `transmission` | `transmission:4.1.3` | Current stable release/channel; retain pin |
| `unpackerr` | `unpackerr:latest` | Current stable release/channel; retain pin |
| `uptime-kuma` | `uptime-kuma:2` | Track supported v2 channel; deprecated latest points to v1 |
| `valheim` | `valheim-server:latest` | Current stable release/channel; retain pin |

The separate `scripts/transmission-diagnostics/Dockerfile` retains Transmission
4.1.3, refreshes its base digest, and gains weekly Dockerfile coverage.

References: [Docker digest pinning](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions),
[Dependabot Docker tag parsing](https://github.com/dependabot/dependabot-core/blob/main/docker/lib/dependabot/docker/tag.rb),
[Dependabot stable/prerelease detection](https://github.com/dependabot/dependabot-core/blob/main/docker/lib/dependabot/docker/update_checker.rb),
[Uptime Kuma update instructions](https://github.com/louislam/uptime-kuma/wiki/🆙-How-to-Update),
[Timescale Docker upgrades](https://github.com/timescale/docs/blob/latest/self-hosted/upgrades/upgrade-docker.md).
