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

See [the runbook](../docs/sunday-edge-workers.md) for releases, state migration,
backup, health checks, Homepage, Prometheus/Grafana, and rollback.
