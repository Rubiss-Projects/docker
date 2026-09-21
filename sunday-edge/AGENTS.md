# Sunday Edge workers

All roles live in this one Compose project. The `dfs` service uses replicas;
never add `container_name` to it. The user explicitly requested this arrangement
instead of one directory per container. `DFS_REPLICAS` in `.env` controls both
the replica count and automatic slot allocation (1–32). Keep those consistent.

Private named volumes preserve Linux permissions for credentials and archives on
Docker Desktop. Do not replace them with NTFS mounts, attach another role's
volume/credentials, or remove a volume. The six compute replicas share only the
DFS volume. No worker may receive a Docker socket or host drive mount.

Preserve non-root execution, read-only root filesystems, dropped capabilities,
no-new-privileges, process limits, CPU quotas, and memory/swap ceilings.
Each role receives only its own encrypted `*.env.secret` file. No secrets belong
in `.env`, image layers, labels, the widget response, or build logs.
`registry.env.secret` belongs only to the deployment host; never load or mount it
in any worker. The deployment helper sends its token to Docker through stdin.

Keep Sunday Edge operational documentation in this file.

## Jev observation rollout (analytics v0.2.12)

Only analytics moves to v0.2.12 for this rollout; the other roles remain at their
compatible v0.2.11 pins. The analytics worker reports `sunday-edge-intelligence-v17`.
Public `.env` enables `JEV_MODE=observe`, pinned to `jev-1.13.0`. There is no Jev
enforcement mode: extraction, mandatory Sol review, accepted signals and lineup
decisions remain authoritative. Observations drain after collection work and use
a separate queue/cache/accounting directory in the existing analytics volume.

`TYPESAFE_API_KEY` belongs only in git-crypt-encrypted `analytics.env.secret`.
It uses the existing TypeSafe account, whose balance is shared with AI Assistant,
but no Discord credentials, environment files or volumes are mounted/copied into
analytics. The worker removes the TypeSafe key from Codex's subprocess environment.

The observer's starting local spending guards are $0.15/day, $2/calendar month and
$3 cumulative (UTC). The cumulative allowance does not reset automatically. These
guards reserve conservatively before calls and reconcile actual API token usage;
they are not provider-enforced billing caps and do not include other apps' usage.
Unknown bills retain reservations. After a crash, a persisted response is reconciled
against its original reservation date. A crash with no durable response halts paid
observation until billing is reconciled. Disable with `JEV_MODE=off`; preserve the ledger.

Deploy through the existing maintenance-wrapped workflow after the app release
publishes the private analytics image. Do not patch files in running containers.
Verify the analytics image/version, `jev_observation` log events, and:

```sh
docker exec sunday-edge-analytics node jev-summary.mjs
```

The read-only summary exposes counts and spending, never credentials or evidence.
Persistent files live under `/data/state/jev-observe/`: `ledger.json`, `pending/`,
`results/` and `attempts/`. Attempt logs preserve each artifact/extractor's provenance
even when multiple attempts share one cached judgment. Retain accounting when
rolling back or disabling observation.
Missing/corrupt accounting stops Jev calls; never delete it to grant new allowance.
Raw source/claim judgments are private, retained for 30 days, and still require
labeled quality evaluation before Jev can acquire routing authority.

No database migration, public endpoint, new volume, role credential sharing, or
resource-limit change is required. Image rollback to analytics v0.2.11 with
`JEV_MODE=off` preserves observation records; follow the normal maintenance wrapper.

## Service overview

[docker-compose.yml](docker-compose.yml) is one stack with six service roles. `dfs` is a
replicated service: six instances by default, with five other containers for
analytics, maintenance, checkpoint recovery, league monitoring, and archival.
The app repository publishes five private, release-versioned GHCR images. Recovery
uses the compute image with its own entrypoint. The web app stays on Vercel.

## Scaling and limits

Change `DFS_REPLICAS` in `sunday-edge/.env`, then run from WSL:

```sh
cd /mnt/e/Docker/sunday-edge
python3 ../scripts/grafana-maintenance.py run --reason planned-scaling -- docker compose up -d --wait
docker compose ps
docker compose stats
```

Supported pool sizes are 1–32. Use the `.env` setting, rather than a standalone
`--scale` override: it also informs slot assignment, polling phases, and alerts.
Compose generates replica names because a fixed `container_name` prevents scaling.
Each replica exclusively locks a logical slot without a Docker socket. Slots 5
and 6 retain manual/urgent reservations; additional slots increase general capacity.
With fewer than five replicas, general slots still handle every type of work.

The defaults cap all eleven containers together at 10.6 CPU cores and 8.625 GiB
memory, with no extra swap allowance. Each DFS replica is capped at 1 CPU/512 MiB;
analytics at 2 CPUs/2 GiB; maintenance at 1 CPU/2 GiB; research at 0.5 CPU/512 MiB;
the league monitor at 1 CPU/1 GiB; and checkpoint recovery at 0.1 CPU/128 MiB. These are ceilings, not reservations.
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
`Rubiss/fantasy-football` repository. See the
[runner credential guide](../scripts/runner-docker-auth.md). Never put registry
credentials in an image, command-line argument, label, or public `.env`.

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
| `sunday-edge-maintenance-data` | `/var/lib/sunday-edge-maintenance` | Maintenance only: preserved result uploads and historical study archives |
| `sunday-edge-research-data` | `/var/lib/sunday-edge-research` | Archive service only: sources and observations |
| `sunday-edge-dfs-data` | `/var/lib/sunday-edge-dfs-simulator` | Legacy research retained; replicas see only the new `runtime` subdirectory |

The migration on 2026-09-12 imported all four directories and verified their complete
file-content manifests, including binary files, symlinks, and empty directories.
Docker owns the live state now. The former directories in the table are historical
source locations; the old systemd units, timers, environment files, installations,
and duplicate data were removed after migration acceptance on 2026-09-13 (UTC).
The one-time importer and disposable migration rehearsal have been retired from
the repository; their implementations remain available in Git history.

Release `v0.2.9` adds candidate research to the maintenance role. Archived source
receipts and paired-lineup artifacts live at `/data/dfs-research` on its existing
private volume. Each durable job replays one NFL week, then yields to queued
imports and calibration; future pre-lock confirmations take priority over history.
The Research page on Vercel only reads bounded summaries and queues work. It
enables scheduling after a compatible maintenance worker reports availability.
Keep the existing 1 CPU / 2 GiB maintenance limits. Resume an interrupted study
from the app so it retains its frozen plan and completed weeks; preserve rejected
or data-blocked studies and their archives. A historical pass does not deploy a
model change: current-season confirmation and a reviewed app release are required.

Historical starts remain disabled until a complete authenticated weekly salary
archive is available. Configure `DFS_RESEARCH_SALARY_URL_TEMPLATE` only in the
maintenance role's environment after verifying all required seasons, including
defenses. The URL needs `{season}` and `{week}` placeholders and HTTPS; redirects
are rejected. Evidence refresh and the candidate tracker work without this
archive. Validate a completed evidence-refresh job during this rollout; do not
claim a historical replay has run while its source dependency is unresolved.

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

Wrap the entire rollback (including the stop) in the maintenance command below.

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
infrastructure. The older `Start Sunday Edge WSL Services` task was removed after
its definition was archived with the migration backup. Its only action was
`wsl -d Ubuntu --exec /usr/bin/true`. The Docker watchdog already invokes WSL during
its regular health checks, and both Docker tasks invoke WSL for Compose recovery,
so the separate Ubuntu startup task was redundant.

## Monitoring and Homepage

### Planned deployment and restart maintenance

`scripts/grafana-maintenance.py` creates two temporary Grafana silences, scoped
to Sunday Edge's existing availability and restart labels. Deployment automation
establishes them before changing this stack and ends availability maintenance on
exit, including failure. It refuses a Sunday Edge deployment if Grafana maintenance
cannot be established. Uptime Kuma maintenance remains a separate integration.

The restart alert counts resets over 30 minutes, so its silence remains for
35 minutes after maintenance ends. Other Sunday Edge alerts are not muted. Each
operation owns separate silence IDs, so overlapping operations cannot unmute each
other. If cleanup cannot run, availability expires at the requested TTL and the
restart silence expires 35 minutes later. Operations must fit within that TTL;
use a longer `--ttl-minutes` for extended work.

For manual deployment, scaling, image rollback, or restart, run from this directory:

```sh
python3 ../scripts/grafana-maintenance.py run --reason planned-restart -- docker compose restart
python3 ../scripts/grafana-maintenance.py run --reason planned-deploy -- docker compose up -d --wait
```

The `run` command also creates and cleans up Kuma maintenance for all five
singleton monitors. For a sequence of lifecycle actions, pass a script as the
command so maintenance covers the whole sequence. Direct `docker restart` or
`docker compose` lifecycle commands bypass these hooks and can still notify.

The Windows watchdog and nightly restart use `scripts/grafana-maintenance.ps1`
through the shared Windows helper. After initially installing/updating the hooks,
run `python3 scripts/install-grafana-maintenance-hooks.py --apply` from the repository
root. The installer backs up the two affected Windows scripts and leaves task
definitions, enabled states, and locking intact. It is idempotent. These host
scripts live outside Git; the installer and the functions they load are versioned.

Windows recovery attempts Grafana maintenance before touching containers. If
Grafana is already unavailable, recovery continues and the fixed nightly mute
remains a fallback. On exit, availability notifications resume and the restart
grace begins. The helper reads the existing Grafana password from the container
without logging it; the username defaults to `rubiss` (`GRAFANA_MAINTENANCE_USER`
can override it). Grafana's published local port 3000 must be reachable from WSL.

### Health and metrics

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

Release `v0.2.10` fixes analytics startup failures when ESPN rejects the multi-day
scoreboard query with HTTP 400. The worker falls back to the same nine inclusive
dates, requires all daily responses, and deduplicates/sorts the resulting games.
An upstream failure still makes `/healthz` return 503; do not suppress that alert
or treat a partial schedule as healthy. For this incident, verify a completed
analytics task and fresh source collection, not just a newly started supervisor.

Release `v0.2.11` adds lossless simulation-player transport compression (worker
`dfs-simulator-v37`, protocol `dfs-simulation-contract-v7`) to fix analytics-rich
leases exceeding the web response budget. Deploy the matching web app before
these images. The web app rejects older workers until the compatible pool
registers; a worker-only rollback to v36 will not restore compute with the v37
web app. No database migration or volume changes are needed.

After rollout, verify all configured compute replicas register as v37, then
generate a fresh Week 2 portfolio with current inputs and the intended planned
entry count. Confirm simulation batches actually complete and entry-readiness
checks pass before export; healthy containers alone do not establish recovery.
Keep the old `BATCH_FAILED` portfolio blocked and preserved for audit.


## Doubtful availability rollout (v0.2.13)

All six image references move to v0.2.13. Compute registers as
`dfs-simulator-v38`; the matching web app refuses older compute workers.
The app and workers preserve DOUBTFUL and block new entry recommendations
containing doubtful players, including legacy Questionable inputs retaining
a Doubtful source status. Already-started late-swap slots remain preserved.
No database migration, volume, credential, resource, or Jev configuration change
is required. The release retains the Jev observer and receipt fixes.

After deployment, verify all six compute replicas register v38. Existing
Week 2 portfolios remain audit records; refresh analytics and regenerate before
exporting a replacement. Rollback requires a compatible app/worker pair; do not
roll workers alone back to v37 while the app requires v38.

## League monitor offload (v0.2.16)

The sunday-edge/watchdog container now runs league, draft, waiver and trade
analysis locally, polling durable MonitorState due times every 15 seconds. Its
own git-crypt-encrypted watchdog.env.secret requires DATABASE_URL,
CONFIG_ENCRYPTION_KEY and CRON_SECRET. Do not mount another role's secret file.
No Vercel queue token, archive volume or new service is required. Existing
Homepage, Kuma and Prometheus endpoints remain on port 9460.

Deploy the matching web revision before promoting these images. The web monitor
consumer now drains legacy deliveries; settings retain durable schedules. The
worker invokes the authenticated POST /api/cron/monitor-watchdog only to publish
DFS reanalysis from the production runtime. It runs the expensive league analysis
and Discord delivery itself. Its supervisor bounds each batch to three minutes;
database claims retain a 30-minute backoff after a killed task.

Verify fresh monitor_completed events and advancing MonitorState.lastSuccessAt,
including existing future due times, before retiring old Vercel consumers. All
six image references must match the app release. A rollback to the old watchdog
also requires restoring the prior web scheduler, since it cannot execute monitors.
