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

Give the `/sunday-edge` Dependabot update job the same read-only registry access
through the repository's Dependabot secret `SUNDAY_EDGE_GHCR_TOKEN`. Its explicit
registry entry supports the private images across the application and Docker
repositories without making the packages public.

After a repository release publishes every image, update the six image references
in this Compose file to that release and merge a passing infrastructure PR. The
existing deploy workflow pulls and updates the running stack. It verifies every
actual container, including all configured replicas. New stacks are intentionally
skipped by automatic deployment until their first manual, verified migration.

## Data and first migration

The production database retains analysis results and durable jobs. Four named,
external volumes hold local state, preserving Linux permissions on Docker Desktop:

| Volume | Original directory | Runtime access |
| --- | --- | --- |
| `sunday-edge-analytics-data` | `/var/lib/fantasy-analytics` | Analytics only: pending batches, evidence, Codex login/history |
| `sunday-edge-maintenance-data` | `/var/lib/sunday-edge-maintenance` | Maintenance only: preserved result uploads |
| `sunday-edge-research-data` | `/var/lib/sunday-edge-research` | Archive service only: sources and observations |
| `sunday-edge-dfs-data` | `/var/lib/sunday-edge-dfs-simulator` | Legacy research retained; replicas see only the new `runtime` subdirectory |

The image and Compose changes must pass before migration. Run the app repository's
Windows E: storage preflight on ben-server. Verify production's web revision,
drain active compute/maintenance leases, and ensure the analytics collector is
between runs. Pull and inspect the release images using the runner's Docker login.

From root in Ubuntu, inspect then execute the migration using an exact validated
compute image (replace `<digest>` with that release's real SHA-256 digest):

```sh
python3 /mnt/e/Docker/scripts/migrate-sunday-edge-workers.py --image ghcr.io/rubiss/sunday-edge-compute@sha256:<digest>
python3 /mnt/e/Docker/scripts/migrate-sunday-edge-workers.py --image ghcr.io/rubiss/sunday-edge-compute@sha256:<digest> --execute
```

The disposable rehearsal is available as `scripts/test-sunday-edge-migration.py
--image <compute-image>`. It verifies byte-for-byte imports (including binary
files, symlinks, and empty directories), copied ownership, volume subpaths, and
eight distinct non-root replica slots without any production credentials/network
access. It removes only its uniquely named, fixture-labelled test resources.

The script refuses existing destination volumes, records legacy unit states,
stops timers/services, preserves source directories and private tar backups under
`/var/backups/sunday-edge-containers/<timestamp>`, imports each volume, and compares
the complete file-content manifest. It changes copied ownership to UID/GID 10001,
clears only the copied analytics process lock, and creates the isolated DFS runtime
subdirectory. It never starts containers, deletes originals, or alters database
rows. A failure leaves the source and any copied data intact for investigation;
do not delete a partially imported volume to blindly rerun the script.

After the manifest verifies all four imports, run `docker compose up -d --wait`.
Check real leases/heartbeats, recovery calls, analytics ingestion, preserved result
archives, and the Codex login. Confirm all old Sunday Edge units/timers are disabled
and inactive. Keep the originals and backups until the migration is accepted.

For an image rollback, stop the affected role, pin the prior compatible image,
and restart it with the same volume. For a systemd rollback after containers have
written new state, stop Docker first and export the latest volumes back to the
original directories with the original service ownership. Never restart stale
systemd copies or restore an old checkpoint over newer data. Re-enable only the
units recorded as enabled in the migration manifest. Never use `down --volumes`.

For the later server move, export all four named volumes while writers are stopped,
verify checksums, restore them as external volumes on the new Docker host, unlock
the encrypted environment files, and start this same Compose stack. Preserve the
database and worker-pool identity. Bind mounts do not need Windows-path rewrites.

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
