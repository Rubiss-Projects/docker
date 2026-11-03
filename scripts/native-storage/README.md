# Native media mount admission (prepared, not installed)

This candidate implements the migration runbook's Docker **daemon** prestart gate.
It has no installer, recovery timer, service-start command or production effect.
Keep it on the preparation branch while Windows remains the production host.
Do not apply the examples to either working Docker Desktop host.

`check-media-mount.py` reads the kernel mount table before touching media paths.
It rejects an absent/duplicate mount, a different server/export or filesystem,
wrong read/write mode, soft NFS, an untested protocol, or nested shadow mounts.
It then requires existing readable/searchable directories and rejects symlinks.
It never creates mountpoints, directories or sentinel files and never writes media.
This checks root/daemon traversal; per-application UID/GID and effective writes
still need the real application fixtures and later acceptance.

The example mounts the tested `Media/data` NFS subdirectory directly at
`/srv/Media`. A normal read-only NFS 4.1 controller fixture verified the same
directory inode/children as the existing share-root mount's `data/` directory;
write attempts were rejected and only that disposable mount was released.
With the repository at `/srv/Docker`, existing `../../Media` binds then resolve
to the actual media tree, preserving container paths and one filesystem for
hardlinks. The share root's fixture/recycle directories are not media roots.
The running source copy mount was unchanged. Confirm the actual native RW mount,
numeric permissions and every required library root after complete inventory;
the example's `.` alone does not establish full library or production readiness.

For the later native installation, stage a root-owned policy and checker, the
reviewed `srv-Media.mount` unit and the Docker service drop-in shown here.
`RequiresMountsFor`, explicit ordering and `BindsTo` cover engine autostarts,
including socket activation and containers with restart policies. A Compose-only
wrapper is insufficient. Verify the installed Docker unit and merged drop-ins on
the actual native OS before activation. Keep SSH/console independent of Docker.
There is deliberately no automatic retry/restart owner.

The `timeout` prestart limits ordinary probes. Hard NFS I/O can remain stuck in
the kernel despite a signal: this does not authorize a lazy unmount, switching to
soft NFS, creating a local library, or proceeding with Docker startup. Mount-unit
activity also does not prove a reachable server during a later network outage.
The real absent-NAS boot and controlled outage acceptance remain pending, with
owner approval before any disruptive test. This preparation does not complete
that gate or coordinated UPS shutdown acceptance.

`startup-plan.json` gives every tracked main-host Compose stack an explicit
keep/replace/defer/archive disposition, startup dependencies and release gates.
Pi definitions are explicitly excluded. Native responsibilities cover T3,
separate native AI, SSH/Tailscale, Caddy fallback, runner and legacy controls.
This is a reviewed-scope candidate, **not permission to activate services**.
Live inventories may include an explicitly identified read-only recovery helper;
it is excluded only when its isolated network and mount restrictions match.
Unknown stacks, services, dependencies or live identities fail coverage review.
The validator flags remaining Windows/WSL/host-gateway references without
claiming the existing definitions are ready for Linux. It needs PyYAML on the
preparation host; the actual mount checker uses only Python's standard library.

Test without installing anything:

```sh
python3 -B -m unittest discover -s scripts/native-storage -p 'test_*.py' -v
python3 scripts/native-storage/check-media-mount.py --config /private/reviewed-ro-fixture-policy.json
python3 -B scripts/native-storage/validate-startup-plan.py --live-inventory /private/source-service-inventory.json --exclude-helper EXACT_REVIEWED_READONLY_HELPER
```

Use an exact read-only fixture policy only for the controller rehearsal. Native
production needs the reviewed RW source and required roots. Controller NFS root
mapping does not prove future server mapping; preserve the active source export
until a separately reviewed change is needed. No write test is performed by this
startup gate. Guard admission alone cannot establish health, frozen verification,
ownership, application correctness or absence of competing writers.

References: [systemd unit dependencies](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html),
[service prestart behavior](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html).

## Native Compose candidates

`overrides/` contains explicit, unapplied candidates for Plex, Channels,
GPU telemetry and Homepage. Compose `!override`/`!reset` replaces the complete
volume list, removing WSL GPU libraries or Windows drive mounts while preserving
application state, media targets, images, GPU reservations, limits and ports.
Long bind syntax disables automatic host-path creation. Keep the base file first
and use its service directory as the project directory so relative paths retain
their meaning. These files require Compose 2.24.4 or later and the reviewed native
NVIDIA runtime; config rendering is not a GPU or application acceptance test.

`validate-native-overrides.py` performs only `compose config`, with interpolation
and service env-file resolution disabled, and checks the intended differences.
It never starts, pulls, installs or restarts a service. Homepage widgets still
need native path review; cAdvisor launch context and n8n's native mounts/workflow
deactivation/importer bypass are separate work. Do not apply these candidates to
either working Desktop host. Native public-port/firewall, mount, per-application
state, writer handoff and hardware-transcode acceptance still precede activation.

Reference: [Compose merge and replacement semantics](https://docs.docker.com/reference/compose-file/merge/).

## n8n: hold restored schedules before server startup

The exact deployed n8n 2.45.5 image supports `unpublish:workflow --all` without
starting a scheduler. In an isolated restore of the existing encrypted checkpoint,
all captured bytes/database counts matched; that supported CLI unpublished all
seven workflows. Workflow export confirmed all seven inactive. Credential export
successfully decrypted both stored records into container tmpfs, inspected only
for count/object shape and removed without displaying values. No provider test,
workflow execution, n8n server or production state change occurred. This was an
online checkpoint; refresh authoritative state at the actual handoff.

The native n8n override bypasses `/files/import-workflows.sh`, removes its old
writable autobrr/cross-seed recovery binds, mounts the repository read-only at
`/srv/Docker`, and retains the original `N8N_USER_FOLDER` nesting/config bind.
Its entrypoint preserves `tini` and calls a read-only database admission check
before the image's ordinary entrypoint. A missing private `n8n/native-startup-policy.json`
fails closed; copy/review the supplied policy example during native preparation.
The default admits **no active or published workflow** and no pending/unknown
execution state. It passed against the restored inactive clone with the exact
image's Node SQLite runtime. Four focused tests cover legacy active workflows,
read-only bytes, exact Sunday version admission and pending execution rejection.

Only after native Sunday SSH/resource/lock/cooldown/missing-telemetry/scale-down
acceptance may the private policy name the single approved Sunday workflow ID,
its exact published version and `nativeValidationCompleted: true`. A different
version, another active workflow or restored pending execution holds startup.
Use supported n8n CLI operations for workflow changes; this guard never writes
the database and never automatically unpublishes Sunday on a later restart.
It checks startup only, not subsequent UI/API edits; maintain the reviewed
activation and single-writer rules. Reinstall any required community modules
from reviewed manifests and validate the native workflow before enabling it.

No n8n service is started by these preparation tools. The clone is a CLI recovery
fixture, not a native functional autoscaler or full application handoff pass.
Do not use this guard as a substitute for frozen recovery, console, per-app,
power or production ownership acceptance. `validate-n8n-native-candidate.py`
renders the candidate without resolving secrets or contacting the engine.

Reference: [n8n Server CLI](https://docs.n8n.io/hosting/cli-commands/).
