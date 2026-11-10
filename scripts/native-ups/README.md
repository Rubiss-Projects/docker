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

