# Sunday Edge workers

`sunday-edge/docker-compose.yml` is one stack with six service roles. `dfs` is a
replicated service: six instances by default, with five other containers for
analytics, maintenance, checkpoint recovery, monitor scheduling, and archival.
The app repository publishes five private, release-versioned GHCR images. Recovery
uses the compute image with its own entrypoint. The web app stays on Vercel.

## Scaling and limits

Change `DFS_REPLICAS` in `sunday-edge/.env`, then run from WSL:

```sh
cd /mnt/e/Docker/sunday-edge
docker compose up -d --wait
docker compose ps
docker compose stats
```

Supported pool sizes are 1–32. Use the `.env` setting, rather than a standalone
`--scale` override: it also informs slot assignment, polling phases, and alerts.
Compose generates replica names because a fixed `container_name` prevents scaling.
Each replica exclusively locks a logical slot without a Docker socket. Slots 5
and 6 retain manual/urgent reservations; additional slots increase general capacity.
With fewer than five replicas, general slots still handle every type of work.

The defaults cap all eleven containers together at 9.7 CPU cores and 7.75 GiB
memory, with no extra swap allowance. Each DFS replica is capped at 1 CPU/512 MiB;
analytics at 2 CPUs/2 GiB; maintenance at 1 CPU/2 GiB; research at 0.5 CPU/512 MiB;
and each scheduler at 0.1 CPU/128 MiB. These are ceilings, not reservations.
Each added DFS replica adds its configured CPU/memory ceiling and twelve scheduled
idle control-plane requests per hour. Edit the role limits in `.env` as needed.

All containers run as UID/GID 10001 with dropped capabilities, no-new-privileges,
read-only image files, bounded tmpfs/logs, and process limits. No host drives,
Docker socket, or host PID/network namespace is exposed. Only internal monitoring
ports are reachable on proxynet; no ports or public proxy are added.

## Credentials and private images

`compute.env.secret`, `analytics.env.secret`, `maintenance.env.secret`, and
`watchdog.env.secret` are encrypted with git-crypt. Each service loads only its own
file. The archive service needs no credentials. Maintenance alone receives the
database URL; the analytics login lives in its own private volume.

Keep GHCR packages private. The deployment runner's dedicated Docker configuration
must have a Linux-compatible login with `read:packages` and access to the private
`Rubiss/fantasy-football` repository. See `scripts/runner-docker-auth.md`. Never put
registry credentials in an image, command-line argument, label, or public `.env`.

On ben-server in Ubuntu, sign in interactively with a GitHub classic personal
access token scoped to `read:packages` (enter the token at Docker's password
prompt, never in the command):

```sh
sudo -u rubiss docker --config /home/rubiss/actions-runner-docker-ops/.docker-ci login ghcr.io --username Rubiss
```

Keep `GHCR_USERNAME` and `GHCR_TOKEN` in git-crypt-encrypted
`sunday-edge/registry.env.secret`. This file is used only by the host-side
`scripts/login-sunday-edge-registry.py`, never by a worker container. Automated
deployments load it before pulling images; manual deployment can run the helper
as the runner user with its dedicated Docker configuration:

```sh
sudo -u rubiss env DOCKER_CONFIG=/home/rubiss/actions-runner-docker-ops/.docker-ci python3 /mnt/e/Docker/scripts/login-sunday-edge-registry.py
```

Give the `/sunday-edge` Dependabot update job the same read-only registry access
through the repository's Dependabot secret `SUNDAY_EDGE_GHCR_TOKEN`. Its explicit
registry entry supports the private images across the application and Docker
repositories without making the packages public.

After a repository release publishes every image, update the six image references
in this Compose file to that release and merge a passing infrastructure PR. The
existing deploy workflow pulls and updates the running stack. It verifies every
actual container, including all configured replicas. New stacks are intentionally
skipped by automatic deployment until their first manual, verified migration.

## Data, backups, and recovery

The production database retains analysis results and durable jobs. Four named,
external volumes hold local state, preserving Linux permissions on Docker Desktop:

| Volume | Original directory | Runtime access |
| --- | --- | --- |
| `sunday-edge-analytics-data` | `/var/lib/fantasy-analytics` | Analytics only: pending batches, evidence, Codex login/history |
| `sunday-edge-maintenance-data` | `/var/lib/sunday-edge-maintenance` | Maintenance only: preserved result uploads |
| `sunday-edge-research-data` | `/var/lib/sunday-edge-research` | Archive service only: sources and observations |
| `sunday-edge-dfs-data` | `/var/lib/sunday-edge-dfs-simulator` | Legacy research retained; replicas see only the new `runtime` subdirectory |

The migration on 2026-09-12 imported all four directories and verified their complete
file-content manifests, including binary files, symlinks, and empty directories.
Docker owns the live state now. The former directories in the table are historical
source locations; the old systemd units, timers, environment files, installations,
and duplicate data were removed after migration acceptance on 2026-09-13 (UTC).
The one-time importer and disposable migration rehearsal have been retired from
the repository; their implementations remain available in Git history.

The private migration backup remains on ben-server in Ubuntu at
`/var/backups/sunday-edge-containers/20260912T231938Z`. It contains the four original
data archives, environment backup, verified manifest, deployment verification,
and cleanup record. `legacy-installation-config.tar.gz` also preserves the retired
service configuration, source files, and extra export files; reinstallable
dependencies are excluded. These are migration-time backups, not current copies
of the live volumes. Preserve their restricted access because they include
credentials and analytics history.

For an image rollback, stop the affected role, pin the prior compatible image,
and restart it with the same volume. Never restore an old checkpoint over newer
data, recreate the retired daemon installation alongside Docker, or use
`down --volumes`.

For the later server move, export all four named volumes while writers are stopped,
verify checksums, restore them as external volumes on the new Docker host, unlock
the encrypted environment files, and start this same Compose stack. Preserve the
database and worker-pool identity. Bind mounts do not need Windows-path rewrites.

## Windows restart and watchdog coverage

Both Windows tasks, `Start Docker Desktop if not running` and
`Docker Desktop Nightly Restart`, use `E:\Scripts\docker-desktop-common.ps1`.
Its discovery includes the `sunday-edge` Compose project through the running
`sunday-edge` container. Recovery runs Compose for the entire project, covering
all six roles and the configured number of DFS replicas. Individual replica names
do not need entries in either task. Every container uses `restart: unless-stopped`.

The shared helper was verified to discover this project and report all eleven
containers healthy through its WSL Compose command. The Windows watchdog remains
enabled. Worker health and availability are monitored by Prometheus, Grafana, and
Uptime Kuma; the Windows tasks retain the existing checks for Docker's critical
infrastructure. The older `Start Sunday Edge WSL Services` task only starts Ubuntu
with `/usr/bin/true`, which also supports the deployment runner. It does not launch
worker daemons.

## Monitoring and Homepage

Prometheus discovers all DFS replicas from Docker DNS, rather than scraping a
load-balanced hostname once. Existing worker metrics, dashboard UID, and alert
UIDs remain in use. Pool availability follows the desired count exported by the
checkpoint scheduler. The memory-pressure alert uses each container's actual
memory ceiling. Supporting roles expose process/scheduler health and task metrics.

The single Homepage widget uses the app's Sunday Edge icon and shows health,
available/configured DFS workers, active compute jobs, and successful jobs in the
last fifteen minutes. It queries only local Prometheus. Missing metrics are shown
as unknown; they do not become a false healthy status. Historical graphs remain
in Grafana, with an instance-label transition at the Docker migration.

Uptime Kuma discovers singleton service health endpoints from their labels. The
DFS pool is monitored per replica by Prometheus and Grafana. Existing n8n recovery
addresses the actual container name, so singleton monitors keep matching names.
Refresh Kuma without restarting SWAG:

```sh
docker exec swag python3 /app/auto-uptime-kuma.py
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker exec prometheus kill -HUP 1
```

Verify every Prometheus target, provisioned Grafana rule, Homepage widget field,
and Kuma monitor after deployment. Normal process health does not guarantee every
upstream source/model request succeeds; review worker logs and failure counters.
