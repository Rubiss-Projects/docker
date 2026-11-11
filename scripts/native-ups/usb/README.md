# UPS USB ownership handoff

This is preparation source. The NAS retains USB ownership until the local driver
and both clients are ready. No power-loss, forced-shutdown or outlet test is part
of this handoff. The existing native guard remains the server shutdown owner;
keep `nut-monitor.service` masked and do not create a killpower flag.

## Prepare before requesting the cable move

1. Verify utility power, no active battery deadline or current-boot shutdown
   intent, the existing protection on both computers, and clean native main.
2. Install the distribution's signed `nut-server` package with its services held
   stopped during configuration. Preserve the existing masked native monitor.
3. Render `ups.conf.example` with the exact physical UPS serial observed on the
   NAS. Confirm APC USB identity `051d:0002`. Install it and `upsd.conf` under
   `/etc/nut`, owned by root with the package's `nut` group and mode 0640.
4. Render `upsd.users.example` privately with the NAS's existing monitor identity
   and password. Grant only `upsmon secondary`; no primary, SET or instant-command
   permissions. Do not put that password in logs, Git, arguments or task text.
5. Promote the reviewed guard and recovery units together. Both load the optional
   root-controlled `/etc/nut/native-ups.env`. Keep its endpoint at the NAS during
   preparation; both units must use the same endpoint after handoff.
6. Validate `telegraf-ups.conf` with the installed collector against the current
   NAS using a temporary test-only server override. Check real status/charge/load/
   runtime and synthetic missing/conflicting/critical flags without any power
   actions. Preserve existing Telegraf inputs, credentials and InfluxDB output.

## Controlled physical move and acceptance

Ask the owner to move only the USB data cable from the NAS to BEN-SERVER. Leave
all UPS power connections unchanged. Start the configured local driver/server
and verify the exact serial, fresh utility-online status and numeric readings.
Do not change guard endpoints while an outage deadline or shutdown intent is
active. Once local utility status is verified, select `127.0.0.1` in the shared
endpoint file and restart only the native guard. Preserve all existing intents.

Retarget the protected gaming-PC guard to BEN-SERVER while preserving its
30-second policy, accepted drain and payload hash admission. The elevated Windows
update requires the owner's UAC interaction; ordinary agent access cannot read
or replace that SYSTEM-protected task. Verify a fresh online observation.

Configure the NAS through its supported Network UPS slave setting with server
`192.168.50.40`, preserving its existing automatic-protection delay and policy.
Verify client communication, the saved monitor identity and fresh NAS status.
Neither Grafana nor the collector controls shutdown or UPS outlets.

Install the collector fragment after local driver acceptance. Its Prometheus
output exposes only UPS data to the existing bridge/native scrape clients;
timestamps and expiration prevent a live collector from serving indefinitely
stale UPS values. Existing InfluxDB output remains available for history.

Switch the existing recording rules, APC dashboard, Homepage card and Grafana
alerts to the verified native collector. Retire `nut-exporter` and the unused old
`apcupsd-exporter` source only after replacement collection and both power clients
are accepted. Keep the APC dashboard UID and existing Grafana notification route.

If a step fails, hold the switch and reconcile the exact state. Before reverting
USB ownership, return both computer guards and NAS protection to the confirmed
source endpoint. Never activate two USB drivers against the same device.

## Configuration references

The collector fragment uses the installed Telegraf 1.40.3
[UPSD input](https://github.com/influxdata/telegraf/tree/v1.40.3/plugins/inputs/upsd),
[Starlark processor](https://github.com/influxdata/telegraf/tree/v1.40.3/plugins/processors/starlark)
and [Prometheus output](https://github.com/influxdata/telegraf/tree/v1.40.3/plugins/outputs/prometheus_client).
The isolated native validation passed all 11 guard/recovery tests, eight
synthetic status cases and a read-only collection from the current NAS source.
No production collector or power ownership changed during validation.
