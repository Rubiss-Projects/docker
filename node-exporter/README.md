# Native host metrics

BEN-SERVER and the Pi use the same pinned Node Exporter release and the existing
Grafana **Node Exporter Full** dashboard (`rYdddlPWk`). Select the host using its
job/nodename/instance variables; do not fork a second host dashboard.

The native exporter reads host procfs, sysfs and mounted filesystems read-only.
Host PID and network namespaces provide host process and physical NIC counters.
It runs unprivileged with no capabilities, writable application mounts or Docker
socket, and listens only on the server LAN address, port 9100. No public proxy or
router forwarding is needed. Prometheus scrapes it as `instance="ben-server"`.

Host availability, CPU, memory and disk alerts are provisioned in
`grafana/provisioning/alerting/linux-alert-rules.yaml`; delivery uses the existing
Grafana notification policy. This exporter has no recovery or shutdown actions.

First installation requires adding this exact rendered stack to the native
deployment admission policy and verifying the pinned Linux/amd64 image before
starting it. Preserve all existing accepted policy entries. The ordinary deploy
runner deliberately refuses unknown stacks and does not start stopped services.
