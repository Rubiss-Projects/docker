# Native Linux monitoring

The Ubuntu host uses its native Telegraf service and the existing InfluxDB output,
organization, bucket and write token. Linux host inputs replace Windows counters.
No Docker socket, Docker group membership, recovery command or second collector
is required. Retired Windows probe/installer sources remain in Git history.

The five-second host probe negotiates Transmission's token, reads and validates
the full `session-stats` response within one three-second monotonic deadline.
Its 64 KiB response bound and nonblocking lock prevent unbounded or overlapping
observations. A failed/censored duration never enters `rpc_seconds`. Integer
flags retain the original InfluxDB field types. `observer=native_linux` separates
these observations from retained Windows Stopwatch history; their absolute
latency baselines are not directly interchangeable.

The thirty-second aggregate probe retains the existing read-only session and
torrent-inventory checks. HTTP 409 endpoint visibility stays separate from
functional success. Neither probe restarts the application or changes torrents.

## Installation

1. Install the native Telegraf package from the [signed InfluxData repository](https://docs.influxdata.com/telegraf/v1/install/).
   The migration validated Telegraf 1.40.3. Keep the existing output privately in
   `/etc/telegraf/telegraf.conf`, enable native CPU, memory, disk and system inputs,
   and verify the collector is running. Do not copy Windows counters or commands.
2. Stage `/etc/telegraf/transmission-rpc-credentials.json` privately as root,
   with only the original `USER` and `PASS` string values. Preserve existing RPC
   authentication; empty strings represent an already unauthenticated endpoint,
   not permission to disable authentication. Never pass values in arguments,
   write them to this repository or broaden the write token's read privileges.
3. Remove only confirmed previous Transmission inputs from the base configuration
   after retaining a protected backup. The managed fragment owns the two probes
   and the loopback endpoint input; the installer rejects duplicates.
4. Run `sudo python3 transmission/install-telegraf-native.py` to check prerequisites,
   then repeat with `--apply`. The installer preserves the base output, backs up
   managed files privately, validates as the actual service account and restarts
   only Telegraf when needed. Repeated identical installs do not restart it. A
   validation failure restores files before touching the running collector.
   If observing a restart times out, inspect that same systemd job before
   changing files or requesting another restart; the candidate and backup remain.
5. Use Grafana's separate existing read credential to verify fresh `platform=native_linux`
   system and Transmission samples. A write-only token may hide buckets and query
   results; that is not evidence of lost data. Keep the existing InfluxQL mapping.

The native server and Pi share the provisioned Node Exporter Full dashboard for
host CPU, memory, filesystem and network metrics. The existing Transmission
dashboard and alert UIDs are preserved; host-latency panels select only native
observations. Historical metric data remains retained. The former Windows and
duplicate native host dashboards are retired.
Missing telemetry and query errors remain distinguishable from successful RPC.

## Validation and recovery

On Linux, run `python3 -m unittest discover -s transmission/scripts -p 'test_native_*.py'`.
Installer tests use disposable files and mocked service commands; installer
permission/rollback tests run only as root. Probe tests use disposable loopback
servers, including a body that trickles past the absolute deadline.

Before restoring a prior collector revision, preserve current configuration and
restore the managed probe files and fragment together from the reported private
backup directory. Validate as `telegraf`, then restart only that collector. Keep
the current credentials, base output, metric history and application volumes.
Docker crash recovery remains independent of metrics. The owner retired the
legacy health-check-triggered restart workflows; inspect failures before taking
action instead of restarting containers automatically from a health alert.
