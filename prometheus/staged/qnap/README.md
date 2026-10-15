# QNAP SNMP activation

The NAS is currently diskless and uninitialized. These files are **staged**:
Prometheus mounts only `prometheus/config`, so it does not load this directory.
There is no exporter container, configured NAS scrape target, alert or restart
automation. Grafana's provisioned `qnap-nas` dashboard shows the pending state.
See the [NAS monitoring runbook](../../../docs/qnap-monitoring.md).

## Collector validation after initialization

1. Enable SNMPv3 in **Control Panel > Network & File Services > SNMP**, with
   authentication and privacy. Use a dedicated SNMP identity and restrict UDP
   161 to the collection host on the LAN. SNMP polling needs no trap destination
   and no WAN port forwarding. Confirm the actual authentication/privacy
   protocols offered by this firmware. The auth example uses SHA/AES; adjust
   only to protocols verified on the NAS.
2. Download `NAS.mib` from that same screen. Record firmware version and the
   file's checksum. Inspect the object definitions before generating anything:
   this firmware's MIB is authoritative, not old QTS examples or an assumed
   enterprise OID. Check the candidate names in `generator.yml`; substitute
   supported equivalents and update the dashboard together if needed.
3. Use a matching stable version of the official Prometheus exporter and
   generator. `v0.30.1` was the latest release checked on 2026-10-15. Recheck at
   activation, pin the runtime image as
   `prom/snmp-exporter:v0.30.1@sha256:<verified-registry-digest>`, and build the
   generator from that same release. Follow the upstream generator build
   instructions; do not run an unrelated binary or a mismatched generator.
4. In a temporary working directory, place this `generator.yml`, the downloaded
   NAS MIB and its dependencies under `mibs/`. Include standard IF-MIB imports.
   With the matching generator binary available, run:

   ```bash
   ./generator generate -m ./mibs -g ./generator.yml -o ./snmp.generated.yml
   ```

   Review warnings and the generated OIDs, metric types and labels. Do not
   suppress unknown objects to make generation pass. No generated collector
   can be checked into this repository until the actual NAS MIB is available.

## Runtime configuration for the activation PR

Create `snmp-exporter/` using the repository's new-service workflow. Keep the
exporter on `proxynet` with no host port or public proxy. Mount the reviewed
generated module file and completed `auth.yml.example` read-only as
`/etc/snmp_exporter/snmp.yml` and `/etc/snmp_exporter/auth.yml`. Use these command
arguments (the generator input itself is **not** a runtime config):

```yaml
command:
  - --config.file=/etc/snmp_exporter/snmp.yml
  - --config.file=/etc/snmp_exporter/auth.yml
  - --config.expand-environment-variables
  - --web.listen-address=:9116
```

Populate `QNAP_SNMP_USERNAME`, `QNAP_SNMP_AUTH_PASSWORD` and
`QNAP_SNMP_PRIV_PASSWORD` only in encrypted `snmp-exporter/.env.secret`, loaded
by Compose. Do not put secret values into generator input, generated config,
Prometheus URLs or logs. The exporter expands those fields from its environment;
missing variables are errors. Do not enable the stock `public_v2` auth.

Add the pinned image to Dependabot, with the next unused Saturday five-minute
slot. Add the appropriate deployment dependency so the exporter is running
before Prometheus starts the new scrape job. Link its Homepage entry to the NAS
dashboard, and monitor exporter HTTP availability using its internal port.
These service/deployment changes belong in the activation PR, not the diskless
preparation change.

## Prove metrics before enabling the scrape job

From the collection network, request
`http://snmp-exporter:9116/snmp?target=NAS_LAN_IP&auth=qnap_v3&module=qnap,qnap_interfaces`.
Replace `NAS_LAN_IP` with the router reservation. Check a successful response,
then compare all retained dashboard values against QuTS hero Resource Monitor
and Storage Manager. Required checks:

| Data | Acceptance check |
| --- | --- |
| CPU and temperatures | Confirm numeric values and percent/Celsius units. Treat unsupported sensors and sentinel values as unavailable. |
| Memory | Inspect actual type and unit. `systemTotalMemEX` / `systemFreeMemEX` can be formatted strings; an info metric's sample value `1` is not one byte. Do not add arithmetic until numeric values and units are verified. |
| Storage | Verify which rows represent the ZFS pool or shared folders and what free/used mean. Do not sum overlapping datasets/quotas or treat volume values as pool capacity. Add storage panels only after RAID creation and comparison with Storage Manager. |
| Network | Use IF-MIB Counter64 octets for throughput. The dashboard converts octets/second to bits/second. `ifPacketsReceivedEX` is packets, not bytes. Map interface names/indexes to the physical active 2.5/10GbE port. |
| Drive health | Validate each reported state and map indexes to physical bays before adding health panels. A successful scrape alone does not prove disk health. |

The supplied dashboard's CPU/temperature queries are candidates from community
dashboard 9330. Revise or remove any that the new firmware cannot supply. RAM,
storage and SMART panels remain deferred rather than showing guessed values.

Only after this verification, replace `NAS_LAN_IP` in `scrape.yml` and merge its
single job into `prometheus/config/prometheus.yml`. Check the full config with
the pinned Prometheus image's `promtool check config`, then deploy through the
normal PR process. Verify `up{job="qnap-snmp",instance="qnap-nas"} == 1`, the
metric panels, gaps on failed collection and the correct units. Update the
dashboard's setup note when activation is complete. No shutdown/restart policy
or alert rule is introduced by this integration.

## Sources

- [QNAP SNMP setup](https://docs.qnap.com/operating-system/quts-hero/6.0.x/en-us/configuring-snmp-settings-42DBF952.html)
- [Download the NAS MIB](https://docs.qnap.com/operating-system/quts-hero/6.0.x/en-us/downloading-the-snmp-mib-AAB5A006.html)
- [Official SNMP exporter](https://github.com/prometheus/snmp_exporter)
- [v0.30.1 generator instructions](https://github.com/prometheus/snmp_exporter/blob/v0.30.1/generator/README.md)
- [QNAP community dashboard 9330, revision 1](https://grafana.com/grafana/dashboards/9330-qnap-snmp/)
