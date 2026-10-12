# APC UPS metrics

This exporter reads the existing native Windows apcupsd NIS service and exposes
Prometheus metrics at `http://apcupsd-exporter:9162/metrics` on `proxynet`.
The USB data cable stays attached to Ben-server. The container has no USB access,
host mounts, Docker socket, published port or public proxy.

```text
APC USB -> Windows apcupsd (127.0.0.1:3551)
        -> Docker Desktop host.docker.internal:3551
        -> apcupsd-exporter:9162 -> Prometheus -> Grafana
```

The existing Homepage APC widget still reads NIS directly; its card links to the
Grafana dashboard. Prometheus stores the new history in its existing
`prometheus_data` volume. No history exists before the first successful scrape.

## Informational scope

The user requested UPS visibility without adding alerts or recovery automation.
This is a narrow exception to the usual new-service Kuma and Homepage-label
steps: there is one existing APC card, no duplicate exporter card, and no Kuma
labels that could invoke n8n container recovery. There are no APC alert rules or
new restart workflows. Docker's standard `unless-stopped` policy remains.

Neither the exporter nor Grafana controls UPS output or performs shutdowns.
Keep the native [monitoring-only configuration and no-action handler](../apcupsd/README.md)
unchanged. Coordinated shutdown of the PCs and NAS is separate work that requires
a tested policy; monitoring alone does not protect against battery exhaustion.

## Configuration and verification

- `.env` contains public defaults only: NIS host/port and timezone. NIS is
  unauthenticated; do not make port 3551 broadly accessible to the LAN.
- The image is pinned by version and multi-architecture digest. Dependabot checks
  it weekly on Saturday at 10:15 America/Chicago.
- The exporter runs as UID/GID 1000 with a read-only root filesystem and no
  capabilities. Its small executable `/run` tmpfs is required by upstream's s6
  supervisor and is owned by the same UID/GID. It has no persistent state.
- Prometheus uses job `apcupsd`, target `apcupsd-exporter:9162`, and stable
  instance label `ben-server-ups` at a 15-second interval.

### Required first-deployment handoff

The push-to-main runner intentionally leaves stopped/new stacks stopped
(`DOCKER_DEPLOY_START_STOPPED=false`). Merging this change therefore does not
bootstrap the exporter. After the merge-triggered deployment finishes, the
deployment operator must run the following from WSL in the clean canonical
checkout before declaring this integration live:

```bash
cd /mnt/e/Docker/apcupsd-exporter
docker compose config --quiet
docker compose up -d
docker logs --tail 30 apcupsd-exporter
```

The runner's `docker compose up -d` also does not reload changes inside the
Prometheus configuration bind mount. As part of that same first deployment,
validate the installed configuration and reload the running process without a
restart. Run the second command only if validation succeeds:

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker exec prometheus /bin/sh -c 'kill -HUP 1'
```

Check the `apcupsd` target and live metric values in Prometheus/Grafana against
`apcaccess.exe status` on Windows. A successful HTTP scrape alone is not proof
that the USB device is communicating. Confirm the current UPS state and timestamp;
missing communication must not appear as a healthy cached reading. Do not test
the integration by unplugging power or running `apctest`/`--killpower`.

Complete the handoff only after `up{job="apcupsd"}` is `1`, UPS status is current,
the Grafana panels show fresh data, and the Homepage card opens the dashboard.
Repeat the validated reload whenever the scrape configuration changes; later
exporter updates can use the runner once the stack is running. This explicit
bootstrap preserves the repository policy of not starting unrelated stopped
services.

## Backout and native Linux migration

To remove this integration, stop this exporter stack, remove its Prometheus job,
validate/reload Prometheus, and remove the provisioned Grafana dashboard and
Homepage dashboard link. Keep the native apcupsd service and Homepage widget if
their live status display is still wanted. Historical series expire under the
existing Prometheus retention policy; do not delete its shared volume.

The current connection works because Docker Desktop forwards
`host.docker.internal` to Windows loopback. Native Docker on Ubuntu does not
provide that same routing automatically. Merely adding a `host-gateway` alias
does not make a host service bound to `127.0.0.1` reachable from bridge containers.
Before Linux cutover, choose and test the UPS host service, narrow Docker-to-host
listener/firewall path, exporter `APC_HOST`, and Homepage widget URL together.
Do not change the current Windows NIS listener to `0.0.0.0` as a shortcut.

Retain the stable `job`/`instance` labels and migrate the existing Prometheus
volume to preserve history. Validate fresh telemetry again after USB access and
network routing have moved. Review Linux package shutdown hooks explicitly;
Windows' no-action handler does not automatically carry over.

References: [container source and runtime requirements](https://github.com/thespad/docker-apcupsd_exporter),
[exporter source](https://github.com/mdlayher/apcupsd_exporter),
[LinuxServer non-root requirements](https://docs.linuxserver.io/misc/non-root/).
