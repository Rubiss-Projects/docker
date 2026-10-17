# QNAP collector moved

The initialized NAS now has a dedicated
[`snmp-exporter` service](../../../snmp-exporter/README.md). Its runbook owns the
NAS MIB provenance, generated modules, SNMPv3 credentials, collection checks and
deployment instructions. Prometheus's `qnap-snmp` scrape job belongs in
[`config/prometheus.yml`](../../config/prometheus.yml); this directory is not
mounted or loaded by Prometheus.

See [QNAP access and monitoring](../../../docs/qnap-monitoring.md) for the LAN
access boundary, Grafana validation, history retention and the deferred
Homepage widget. Erase/scan percentages remain on the separate
[migration progress page](https://nas-linux-migration-field-guide-2026.rubiss89.chatgpt.site/progress).
