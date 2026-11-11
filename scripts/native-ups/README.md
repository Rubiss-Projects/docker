# Native UPS shutdown guard

This is the source for the guard already running on the native Linux server.
It preserves the admitted Windows policy during the migration: the NAS owns the
UPS USB connection, and the server reads `qnapups` status from
`192.168.50.91:3493`. The historical `nas-migration-ups` unit and state-directory
names are retained so source promotion does not change the working protection.

The guard waits 30 seconds after confirmed on-battery status before draining
running containers and requesting normal OS poweroff. Low battery while on
battery, forced shutdown, or confirmed UPS-off status trigger the critical path.
A confirmed return to utility power clears the battery deadline. Communication
loss alone does not admit shutdown; loss after a known battery event preserves
its deadline. A boot-bound, exclusive intent prevents competing shutdowns.
Failures draining applications still lead to an ordinary OS shutdown request.

NUT status traffic is unauthenticated and unencrypted on the trusted LAN. Keep
the NAS endpoint restricted to admitted clients. The exporter remains a separate,
read-only telemetry service; it carries no shutdown credentials. This guard
does not control UPS outlets or start Docker containers.

## Current deployment acceptance

For the existing host, first compare the repository policy, tests and unit with
the deployed files under `/usr/local/lib/nas-migration/` and
`/etc/systemd/system/nas-migration-ups.service`. The source promotion is accepted
only when their content matches, the unit remains enabled/active, the current
observation reports online power, and the decision tests pass. Line-ending
normalization can be compared separately from executable policy content.

An exact source match needs no service restart or application interruption.
Keep the existing state directory and any shutdown intent. Reconcile a retained
intent before starting another guard. The owner waived a physical outage test;
decision tests and online observations do not claim an exercised poweroff.

## Rebuild on a replacement native host

Use these commands only as part of the replacement host's admitted bootstrap,
after its NAS/UPS identity and trusted-client access are verified:

```sh
sudo install -d -m 755 /usr/local/lib/nas-migration
sudo install -m 644 native_ups_guard.py test_native_ups_guard.py /usr/local/lib/nas-migration/
cd /usr/local/lib/nas-migration
python3 -B -m unittest -v test_native_ups_guard
python3 -B native_ups_guard.py --observe
sudo install -m 644 /path/to/checkout/scripts/native-ups/nas-migration-ups.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/nas-migration-ups.service
sudo systemctl daemon-reload
sudo systemctl enable --now nas-migration-ups.service
```

Run the first install command from this source directory; replace the explicit
checkout path for the unit. The service uses root to request ordered container
drain and normal shutdown. Its systemd restrictions leave only its private
state directory writable. Review a policy or endpoint change before installing
different bytes on an active host.

CI runs the pure decision tests on Linux. They exercise utility power, battery
timing, critical flags, invalid/conflicting data and loss of status after a
battery event without invoking application drain or poweroff.

## Recover after a protective shutdown

The November 11 voltage event exposed Docker's `unless-stopped` behavior:
containers explicitly drained by the guard stay stopped on the next boot.
The guard now records the running Compose container IDs, image IDs and ownership
in its private state directory before draining. Failure to record recovery state
still allows the existing protective shutdown to proceed.

`nas-migration-ups-restore.service` runs once after Docker starts and before the
HTTPS startup helper. It requires a previous-boot manifest, confirmed utility
power, unchanged container/image/Compose identities, and native mount/policy
admission for every affected project. It starts only the saved stopped IDs,
checks utility power again before each start, and records completion. Missing
or changed identities hold recovery for operator reconciliation. Dormant stacks
and unmanaged temporary containers are excluded.

Pending identities survive a second outage during partial recovery. A new
shutdown intent on the current boot holds further starts, including if utility
power returns before the requested shutdown finishes. The unit preserves the
media mount's admitted access mode inside its sandbox; admission still verifies
the exact NFS source, mount options and directory access.
The deployment account's home is read-only, allowing its installed Compose
plugin and Docker configuration to be read during admission without permitting
home-directory writes.

Install the reviewed `native_ups_restore.py` beside `native_ups_guard.py` in
`/usr/local/lib/nas-migration/`, and install the new restore unit in
`/etc/systemd/system/`. Validate with `systemd-analyze verify`, reload systemd and
enable the restore unit. Promote the reviewed guard only while utility power
is confirmed and its observation has no active battery deadline. Preserve all
existing state and shutdown intents. The new unit has no periodic timer or
restart loop. The owner-waived physical outage test remains waived; unit and
identity/admission checks must not claim an exercised outage.

