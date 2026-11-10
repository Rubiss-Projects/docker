# Kuma sync protection

This init hook runs before `swag-auto-uptime-kuma`. It retains the tested initial
`info` event barrier and replaces the mod's reviewed entry point with `sync.py`.
Unknown installed module or entry-point hashes stop installation for review.
The existing read-only directory mount includes both files on container recreation.

The reconciler reads running containers with `swag.uptime-kuma.enabled=true`.
For an existing `swag`-tagged monitor it applies only explicitly configured
`swag.uptime-kuma.monitor.*` fields using Kuma's edit API and the original ID.
Unspecified settings, including notification choices and saved pause state, remain
unchanged. Label defaults and default notifications apply to new monitors only.
An explicit `notificationIDList` label sets that list without adding defaults.
Identity and pause fields cannot be controlled through labels.

Absent containers and empty groups are retained. No delete, purge, pause, or resume
operation is performed. Retiring a monitor is a separate deliberate operation.
The upstream mod's old configuration cache is retained but no longer drives edits.
Duplicate tags, ambiguous parent groups, and unlinked monitors with the requested
name stop reconciliation for manual review. An interrupted add/tag pair leaves its
new record intact; do not delete and recreate an existing monitor to resolve it.

To inspect the plan inside SWAG without changing monitors or groups:

```sh
docker exec swag /command/with-contenv python3 /app/auto-uptime-kuma.py --dry-run
```

The normal no-argument init invocation applies the plan. Logs show monitor names,
IDs, and changed field names, without dumping label values or credentials. A
container-local file lock prevents overlapping reconciler executions. The former
upstream purge CLI is intentionally unavailable.
