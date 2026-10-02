# Prepare application storage before VirtioFS

The October 2, 2026 trial presented a protected Windows directory as UID/GID
1000:1000 while retaining its 700/600 modes. PostgreSQL could not use it. Both
production PostgreSQL clusters now use native Docker volumes. This runbook covers
the other identified ownership risks; it does not certify the complete VirtioFS
backend or authorize a WSL restart.

## Findings and proposed changes

| Service/state | Current writer and finding | Preparation |
| --- | --- | --- |
| Grafana | UID 472:0; existing `grafana.db` is 472:0/640. Mapping it to 1000:1000 denies database access. PUID/PGID environment variables do not change this image's user. | Full data directory to `grafana_data`; retain UID 472 and the installed image. |
| Prometheus | UID 65534:65534; existing `queries.active` is 65534:65534/644. Mapping its owner denies writes. | Full data directory to `prometheus_data`, preserving its nested `data/` child. |
| Tracearr Redis | UID 999:1000; existing files are broadly writable, but the installed entrypoint selects umask 0077 and new private files would lose access if mapped to 1000. | Full Redis directory, including multipart AOF, to `tracearr_redis_data`. |
| Tracearr backups | App UID 1001:65533; backup root is writable today. New owner-writable subdirectories would not remain writable if remapped. | Existing backup directory to `tracearr_backups`; export backup archives outside the Docker disk. |
| Bitwarden application | UID 911:911; key-storage and license directories are already 1000:1000/755 and fail its read-only write-access check on Plan9. | Use the installed entrypoint's PUID/PGID settings, both 1000, for the app. PostgreSQL remains unchanged. |

Read-only inventory covered all 47 running containers and 29 services with
Windows-backed writable application mounts. Sonarr/Radarr/Prowlarr/Bazarr,
Bookshelf, Plex, Transmission, Seerr, Autobrr, Cross-seed, Speedtest Tracker and
InfluxDB writers matched UID 1000. Root-run state consumers and native-volume
services do not show this specific non-root ownership mismatch. Calibre's app
runs as 1000; its separate nginx worker is not its library database writer.
There is no evidence requiring every database or any media/torrent payload to move.

This is a bounded metadata/startup-source assessment, not a recursive audit of
all application files or a storage-correctness pass. A disposable tmpfs model
reproduced the permission denials and matching-owner successes (12 cases). A
separate exact-image fixture confirmed Bitwarden's vendor user-creation block
accepts PUID/PGID 1000. Neither fixture ran a real application database or VirtioFS.
The host stayed on Plan9; no production data, permissions or services changed.

## Cutover mapping

| Windows source, relative to repository | Required external volume | Container destination | Approximate current bytes |
| --- | --- | --- | ---: |
| `grafana/data` | `grafana_data` | `/var/lib/grafana` | 543,654,565 |
| `prometheus/data` | `prometheus_data` | `/prometheus` | 2,933,768,245 |
| `tracearr/data/redis` | `tracearr_redis_data` | `/data` | 7,192,383 |
| `tracearr/data/backup` | `tracearr_backups` | `/data/backup` | 12,890,844 |

Sizes are live metadata samples, not cold inventories or measured copy times.
The volume root receives the **contents** of each listed source directory.
Prometheus's current TSDB is `prometheus/data/data` on the host and
`/prometheus/data` in the container. Do not flatten it or start at `/prometheus`.

## Deployment boundary and sequence

Keep the preparation PR unmerged until a noticed per-service cutover is ready.
Use `[skip deploy]` for the merge so the runner cannot race data preparation.
External volumes refuse if missing, but an empty or incomplete existing volume
is still dangerous: Compose does not validate copied data. No ordinary deployment
may select these definitions until the cold copy and verification have passed.

1. Use one maintenance owner and account for deployment/intake/restart automation,
   including n8n. Confirm the actual current mount writers, exact installed images
   and free Docker-disk/host space. Save the original Compose/config and selected
   application settings. Keep Windows, WSL, Docker, networking and unaffected
   media/download services running.
2. Work one group at a time: Grafana; Prometheus; Tracearr app then Redis; Bitwarden
   app with its known API automation held. Stop consumers before their writable
   state. Require an ordinary clean stop and no replacement writer before copying.
   Do not stop the native PostgreSQL servers for these changes.
3. Copy each complete stopped source to its own new, empty native volume using an
   already-installed pinned helper, network none, source read-only and
   `volume-nocopy`. Preserve numeric ownership, permissions, links and all files.
   Retain the original source untouched as the cold migration snapshot. Keep a
   protected verified archive outside Docker's disk; no helper mounts media.
4. Compare source/destination path sets, regular-file lengths and SHA-256 hashes,
   ownership, modes and links while writers remain stopped. Require the expected
   database/state files, not just a successful copy exit or volume existence.
   Check Grafana's copied SQLite read-only; check copied Redis RDB/multipart AOF
   without repair. Inspect copied Prometheus blocks/WAL with the matching tools;
   preserve the whole directory even if a file is not interpreted by a checker.
5. Deploy only the selected service(s), from WSL, with `--no-deps --pull never
   --no-build`. Redis starts before the Tracearr app. Verify the actual new volume
   mounts, runtime users, application readiness and retained state/settings. Check
   Grafana dashboards/data sources, Prometheus existing history and new scraping,
   Redis persistence plus Tracearr's existing library/history checks, and
   Bitwarden existing vault/key availability plus writable key/license paths.
   Tracearr's previously agreed signed-in/UI/Socket.IO exception remains explicit.
6. Update backup selections to the volumes before restoring normal controls.
   Observe the services on Plan9 first. VirtioFS activation is a separate noticed
   host restart with its existing exact-config backout.

Plan 30–60 minutes for the grouped work until copy throughput is known; actual
service stops depend on copy/verification and startup, not the byte count alone.
Grafana dashboards and metric collection have gaps while those services stop;
Tracearr tracking pauses; Bitwarden synchronization is temporarily unavailable.
Plex playback, torrents and the native database servers need no planned restart.
Do not turn a slow copy into a forced shutdown or an unbounded outage.

## Backout and future backups

Before the first write to a new volume, the untouched Windows source is current;
an incomplete copy can be abandoned and the original service definition recovered
on Plan9. After the first new-volume write, that volume is current. A failed
VirtioFS trial returns the host to Plan9 **while keeping the current volumes**.
Never select the stale Windows snapshot or restore an old archive automatically.
A storage reversal needs a new consistent copy of current state into a new
destination, with verification before selection.

Bitwarden's user change preserves its existing config, identity certificate,
attachments, license files and database. If it needs recovery, retain current
state and verify access under the selected user; reverting the user alone can
reintroduce the original unwritable-directory condition. Do not replace keys,
weaken permissions globally or initialize a new config to make health pass.

Future backups must include `grafana_data`, `prometheus_data`,
`tracearr_redis_data`, `tracearr_backups`, and the already-native PostgreSQL volumes,
with the appropriate writers stopped or an application-supported consistent
backup. Save read-only deployment sources and secret overlays separately.
An application backup retained only in `tracearr_backups` shares the Docker disk's
failure domain: export it to protected host/off-host storage. Retain old sources
until the owner separately approves their removal.

## Remaining validation

These changes address the observed ownership pattern. They do not prove VirtioFS
locking, fsync/durability, every startup hook, or every app's complete workflow.
The next migration still needs ordinary startup, write/persistence and recovery
checks. UID-1000 matching is a lower-risk classification, not a universal pass.
The two disabled Docker watchdog/nightly tasks and their false localhost/Plex
probe remain a separate repair; this storage work does not re-enable them.
