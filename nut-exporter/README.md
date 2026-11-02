# NUT UPS telemetry

Read-only telemetry for the planned UPS USB data connection to the NAS. The
existing Windows apcupsd service, APC exporter, Prometheus job and Grafana
dashboard remain intact through this preparation. The new path is not active
UPS protection and does not control shutdown, restart or UPS output.

The pinned official DRuggeri exporter reads the NAS NUT server on the LAN. It
has no host port, public route, USB access, persistent mount, Docker socket or
credentials. Device-info labels are disabled. Like the existing APC exporter,
it intentionally has no Kuma recovery labels or alert rules: this is an
informational collector, represented by a manual Homepage card.

## Staged handoff

Before the physical USB data move and supported NAS network-master setup,
`up{job="nut"}` will be zero and the new dashboard will show unavailable.
This is expected, not a reason to restart production. The exporter image's
`/metrics` healthcheck confirms only its HTTP process. Prometheus must scrape
`/ups_metrics`; a successful empty response is also not valid UPS telemetry.

Learn the actual NAS UPS name and trusted-client source address during the
supported handoff. Default discovery requires exactly one UPS. If multiple
UPS devices are returned, configure an explicitly verified `ups` scrape
parameter; never choose one by guess. If the NAS requires read authentication,
review a least-privileged account separately. Do not provide NAS administrator
or shutdown credentials to the exporter. NUT LAN traffic is not TLS; restrict
NAS access to the trusted client and keep it off public routes.

The exporter supports per-request target overrides. Its internal port must
remain limited to trusted container clients; do not publish it or proxy it
externally. This stack does not edit NAS permissions or services.

## Metrics and displays

The `nut` Prometheus job and `/d/nut-ups` dashboard are separate from historical
`apcupsd` observations. Recording rules require successful scrapes, samples
less than 45 seconds old, and an active recognized UPS status. Missing or
empty status, failed scrapes and old samples produce availability zero and
hide numeric readings. Missing individual measurements remain missing.

Availability means usable telemetry, not healthy power. Online and on-battery
are separate flags: `OL=0` alone does not mean `OB=1`. Runtime is the UPS's
changing estimate, not a tested duration. Estimated watts use reported load
percentage times reported nominal real watts; they are not a wattmeter reading.

Homepage v2.7.0's native `prometheusmetric` widget uses one explicit query per
field. Unavailable values render `-`, not fabricated zero charge or runtime.
The existing APC card remains the current view until real NAS data is verified.

## Deploy without interrupting production

Use the repository PR/review workflow. Merge this initial handoff with
`[skip deploy]` in the merge commit: the normal deployment runner would recreate
existing affected stacks. Wait for that workflow to acknowledge the skip before
updating the clean canonical checkout. Then, from the normal WSL context:

1. Start only this new stack: `docker compose --env-file .env up -d` from
   `/mnt/e/Docker/nut-exporter`. Do not recreate Prometheus, Grafana or Homepage.
2. Validate `docker exec prometheus promtool check config /etc/prometheus/prometheus.yml`.
3. Reload with `docker exec prometheus /bin/sh -c 'kill -HUP 1'`. Do not use
   Docker's kill API, which changes restart-policy bookkeeping.
4. Verify `prometheus_config_last_reload_successful`, the new target and recording
   rules; APC measurements must still be fresh. Grafana's file provisioner polls
   every 30 seconds. Check the new dashboard and Homepage configuration without
   restarting either service. Record original container IDs/start times.
5. Keep the handoff pending until real NAS status/charge/runtime readings are
   reviewed and source-loss behavior is checked. This does not authorize moving
   mains cables or testing a shutdown/outage.

Backout: stop only the new exporter, revert its additive monitoring configuration
through a reviewed change, validate and reload Prometheus. APC monitoring and its
history remain available. Never erase TSDB data or restart production to back out.

## Focused validation

With the repository's pinned Prometheus image and this checkout mounted at
`/workspace`, run `promtool test rules /workspace/nut-exporter/tests/telemetry.test.yml`.
These cases cover online/battery, failed scrape, absent/empty status, missing
individual measurements and stale samples retained by lookback. A separate
private Linux-container fixture exercises the exporter protocol and failure
responses; it does not establish real NAS or shutdown compatibility.

Sources: [exporter](https://github.com/DRuggeri/nut_exporter/tree/v3.3.0),
[Homepage widget](https://gethomepage.dev/widgets/services/prometheusmetric/),
[Prometheus rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/).
