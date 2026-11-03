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

The example mounts the Media share root at `/srv/Media`; the preseeded media tree
is **under `data/`**. Final Compose paths must explicitly resolve to that tree,
without accidentally using the share root, fixture directory or recycle bin.
Review the exact native mount/path layout and every required library root before
replacing example values. Do not infer final production admission from `data/`
existing while the online copy is still running.

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
