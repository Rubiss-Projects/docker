# Native media mount admission (prepared, not installed)

This candidate implements the migration runbook's Docker **daemon** prestart gate.
It has no installer, recovery timer, service-start command or production effect.
Keep it on the preparation branch while Windows remains the production host.
Do not apply the examples to either working Docker Desktop host.

`check-media-mount.py` reads the kernel mount table before touching media paths.
It rejects an absent/duplicate mount, a different server/export or filesystem,
wrong read/write mode, soft NFS, an untested protocol, or nested shadow mounts.
Linux `O_PATH` plus the descriptor's `mnt_id` verifies that pathname lookup
actually reaches the admitted mount, rather than a hidden mountinfo record
under an overmounted ancestor. This identity is checked before and after root
probes. It is a startup observation, not a lock against later namespace changes.
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
[service prestart behavior](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html),
[Linux descriptor mount identity](https://man7.org/linux/man-pages/man5/proc_pid_fdinfo.5.html).

## Native Compose candidates

`overrides/` contains explicit, unapplied candidates for Plex, Channels,
GPU telemetry, Homepage and InfluxDB. Compose `!override`/`!reset` replaces the complete
volume list, removing WSL GPU libraries or Windows drive mounts while preserving
application state, media targets, images, GPU reservations, limits and ports.
Long bind syntax disables automatic host-path creation. Keep the base file first
and use its service directory as the project directory so relative paths retain
their meaning. These files require Compose 2.24.4 or later and the reviewed native
NVIDIA runtime; config rendering is not a GPU or application acceptance test.

`validate-native-overrides.py` performs only `compose config`, with interpolation
and service env-file resolution disabled, and checks the intended differences.
It never starts, pulls, installs or restarts a service. Homepage adds a read-only
NAS bind at `/media` and a read-only file bind for `homepage-widgets.native.yaml`.
The latter reports the local application-config filesystem and NAS filesystem,
replacing the old `/c` and `/e` widget paths. Weather/date/resource options remain
unchanged and no host-root filesystem bind is added. The resources widget's
CPU/memory readings describe its container, not host-level metrics; native
sensors and actual filesystem reporting still need runtime acceptance.

The InfluxDB candidate changes only its shutdown signal and grace period:
`SIGINT` with two minutes to finish. A separate, network-isolated 2.9.1 cold-copy
rehearsal listed 18 measurements and returned a historical row with the existing
read token. `SIGTERM` reproduced exit code 2; the copy then recovered and exited
cleanly with `SIGINT`. Original files remained unchanged and the original service
stayed stopped. This does not establish native-host application acceptance.

Do not apply these candidates to either working Desktop host. Native cAdvisor
data-root/containerd/cgroup/metrics, public-port/firewall, mount, per-application
state, writer handoff and hardware-transcode acceptance still precede activation.

Reference: [Compose merge and replacement semantics](https://docs.docker.com/reference/compose-file/merge/).
See also [Homepage resources](https://gethomepage.dev/widgets/info/resources/).

## Deferred native deployment context

`examples/native-host-context.patch` is an **unapplied** host-context candidate,
not a migration installer. It preserves the current Windows/WSL default, adds an
explicit `native-linux` dispatch that avoids Windows cAdvisor delegation, and
proposes native runner labels and `/srv/Docker` for the main-host workflow. The
trusted-main restriction, read-only workflow token, stopped-service behavior and
Pi jobs remain. The native job omits the contribution-fork installer because that
installer enables a deferred timer and immediately starts a job.

Check applicability without modifying the checkout:

```sh
git apply --check scripts/native-storage/examples/native-host-context.patch
```

Keep the patch unapplied while Windows owns production. Host context alone does
not establish native acceptance. The example now checks the entire changed,
dependency and dependent stack plan before creating monitoring maintenance or
running container operations. It selects the reviewed base plus required native
overlay and rejects newly introduced Compose service keys. Required overlays
cannot silently disappear and fall back to Windows definitions. The media mount
guard also runs before deployment.

`check-deployment-admission.py` reads a **separate private**
`/etc/nas-migration/native-deployment-policy.json`. The supplied
`native-deployment-policy.example.json` deliberately denies all deployment.
The private directory/file must be root-owned and not writable by group/others;
the loader rejects policy-file symlinks and duplicate JSON keys. Do not place the
private policy in the deployment checkout. A `keep` disposition in
`startup-plan.json` remains planning intent and never grants activation by itself.

After the actual native phase, per-application, state/writer and route/power
gates pass, a reviewed private policy may set `nativeAcceptanceCompleted: true`
and individually name accepted `releasedStacks`. It binds the startup plan's
canonical JSON digest, obtainable without granting release:

```sh
python3 scripts/native-storage/check-deployment-admission.py --repo /srv/Docker --plan-digest
```

Formatting and line endings do not change that semantic digest. Changing a
service list or disposition requires a new reviewed release. Unknown, deferred,
archived and replacement stacks are held even if someone lists them in a private
policy. Every selected stack's compiled service keys must still match the plan;
`docker compose config --services` is the only Docker command used by this
checker, with renderer diagnostics kept private. Its recipe query returns paths
only; it never starts an app, downloads an image or applies the patch.

Maintenance installers default to an empty allowlist. A later native installer
step must explicitly invoke the checker's `--installer scripts/<name>` mode
against its reviewed SHA-256 before execution. That check never executes an
installer. The current candidate removes the main-host contribution-fork step;
it adds no automatic installer/schedule step, and Pi jobs remain separate.

Finish the actual native definitions and prove mount/state/permissions, native
cAdvisor and trusted deployment behavior. Register and enable
the destination runner last, without overlapping deployment owners. Do not apply
the context patch and assume that legacy service definitions or installers are
safe on Ubuntu. Actual network/firewall, native runtime and handoff gates remain.

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
