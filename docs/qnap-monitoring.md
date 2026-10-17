# QNAP access and monitoring

The TS-664 is initialized and runs QuTS hero **h6.0.2.3591 build 20260819** at the
router-reserved address `192.168.50.91` on its installed 10GbE NIC. Drive
qualification is in progress; no production storage pool has been created.
The SNMP collector supplies Grafana independently of the deferred Homepage
statistics widget.

## Access

- Normal bookmark: <https://nas.benlawson.dev/>, which redirects to the NAS-only
  HTTPS listener at <https://nas.benlawson.dev:4443/> through Ben-server's SWAG.
- Direct fallback: <http://192.168.50.91:8080/>. Bookmark this before the Ubuntu
  migration: the HTTPS route is unavailable while Ben-server/SWAG is offline.
- `nas.benlawson.dev` resolves to Ben-server's LAN address `192.168.50.40`.
  The existing wildcard certificate covers the hostname. The router's `nginx`
  rule forwards WAN TCP 80/443 to Ben-server, confirmed by the owner on October
  15, 2026. Therefore the shared 443 listener only redirects: it never proxies
  this hostname to the NAS. Private DNS alone would not protect a 443 vhost.
- SWAG publishes the separate listener only on `192.168.50.40:4443`. No WAN
  forwarding or Cloudflare Tunnel ingress is added for this port. The actual NAS
  proxy exists only on that listener. Keep this binding and the router boundary
  when moving SWAG to Ubuntu; do not forward 4443 or enable a NAS tunnel route.
- The private listener also rejects requests carrying Cloudflare's `CF-Ray`
  header as a guard against accidental tunnel routing. Docker Desktop can hide
  client IPs, so a private-address allowlist alone would not establish LAN-only
  access on the already forwarded port 443.

After access or firmware changes, verify login and logout through HTTPS,
redirects remaining on the hostname, and any WebSocket connections used by the
NAS UI. If the NAS HTTP/HTTPS ports change, update the proxy and monitoring URLs
in the same PR. The router reservation follows the installed 10GbE card; retain
the NAS's `.91` address when migrating the surrounding services.

## Grafana collection during drive qualification

- Homepage Hardware contains a NAS link and HTTP reachability indicator. A green
  indicator means the web endpoint responds, not that storage is healthy.
- Grafana's [QNAP NAS dashboard](https://grafana.benlawson.dev/d/qnap-nas) is
  provisioned from the repository and reads the `qnap-snmp` job with
  `instance="qnap-nas"`. Check collection and individual readings after deployment
  using the validation steps below.
- [`snmp-exporter`](../snmp-exporter/README.md) runs on Ben-server's `proxynet`
  without a published host port or public proxy. Prometheus polls the NAS through
  this exporter every 60 seconds. Credentials belong only in its encrypted
  `.env.secret` overlay, not in scrape URLs, dashboard JSON or generated modules.
- The NAS uses a dedicated SNMPv3 identity with authentication and privacy:
  **SHA authentication and DES privacy**. This firmware's settings expose
  **CBC-DES**; AES is not selectable. The SNMP form exposes no per-source access
  restriction. Keep UDP 161 on the LAN with no WAN forwarding; polling requires
  no trap destination. Revisit protocol and source-restriction options after a
  firmware change.
- Runtime modules are generated with official SNMP exporter **v0.30.1** tooling
  from this NAS's downloaded `NAS.mib`, SHA-256
  `0cf58b39ad5c17737a2237f7e9d0a5359d8063d50a72acadd8e74ebe807a8fe9`.
  The service runbook records generation and validation details; the former
  staging directory now points there.
- Prometheus retains **15 days** of history under the existing retention
  settings. SNMP history begins with successful collection; this activation
  does not backfill earlier tests. The migration monitor's existing evidence
  files remain a separate record.

Missing or unsupported temperatures and health readings must remain unknown.
A successful scrape proves collection works, not that a drive passed
qualification. Do not turn a missing sensor, an invalid temperature sentinel or
an unverified SMART state into a zero or green healthy status. Map each reported
disk index to the physical bay before interpreting it.

SNMP does not provide the migration page's erase/scan progress integration.
Follow the separate [migration progress page](https://nas-linux-migration-field-guide-2026.rubiss89.chatgpt.site/progress)
for per-drive jobs and percentages. These read-only collectors do not start,
stop or advance drive tests and add no NAS alert rules or restart/shutdown actions.

## Remaining activation checks

Follow the [physical setup and drive qualification plan](https://nas-linux-migration-field-guide-2026.rubiss89.chatgpt.site/physical-setup)
for storage actions. Enabling monitoring does not authorize erasure, pool
creation or interruption of an active test.

1. Validate the generated exporter configuration and the final Prometheus
   configuration before deployment. Confirm successful real NAS samples and
   `up{job="qnap-snmp",instance="qnap-nas"} == 1` after deployment.
2. Compare CPU/system/disk temperatures and drive/bay labels with the NAS
   interface. Confirm the active network interface and octet-counter units.
   Unsupported OIDs stay absent. Recording temperatures is useful during
   testing but is not a substitute for SMART and surface tests.
3. This firmware's memory values were verified as numeric bytes and are
   collected as gauges. Drive status is the NAS's raw text; its info metric
   value `1` is not a health code. Recheck units, sentinels and ID/serial bay
   mappings after firmware or drive changes. See the collector runbook for
   the activation comparisons.
4. After the accepted drives form the production RAID5 pool, compare capacity and
   usage panels against QuTS hero. Validate bytes versus display units, pool
   versus shared-folder/volume semantics, snapshots and reservations. Only then
   enable storage panels that agree with the NAS and the Homepage widget after
   its separate account prerequisites below are satisfied.
5. Verify the resulting readings in Prometheus, Grafana and, once enabled,
   Homepage before the media copy.

## Homepage widget activation — deferred

The SNMP collector does not enable this widget. Wait for a verified production
pool and create a dedicated local account, initially with the **System Monitoring**
delegated role and no share access. Test the API with that role before granting
anything broader; do not reuse the interactive administrator. Homepage's current
widget does not support an OTP login flow.

Store `HOMEPAGE_VAR_QNAP_USERNAME` and `HOMEPAGE_VAR_QNAP_PASSWORD` in
`homepage/.env.secret`, which is already covered by git-crypt and loaded by the
Compose stack. Confirm the staged Git blob is encrypted before committing it.
Recreate Homepage through the normal deployment when those environment variables
are added. Add this block to the existing **QNAP NAS** card in
`homepage/config/services.yaml` only after the prerequisites above pass:

```yaml
        widget:
          type: qnap
          url: http://192.168.50.91:8080
          username: "{{HOMEPAGE_VAR_QNAP_USERNAME}}"
          password: "{{HOMEPAGE_VAR_QNAP_PASSWORD}}"
          fields: ["cpuUsage", "memUsage", "systemTempC", "poolUsage"]
```

Check the widget's `poolUsage` carefully: Homepage documents it as an aggregate
of reported volumes, which is not necessarily the physical ZFS pool utilization.
Omit that field if the semantics or figures do not agree. Selecting only CPU
fields does not eliminate the widget's volume API request, so wait for the
verified pool before enabling it. Update the card description once active.

## Validation and rollback

Validate Nginx with `docker exec swag nginx -t` before a graceful reload. The
initial additional port mapping requires recreating only the SWAG container;
subsequent config-only updates can use a graceful reload. Verify the browser
trusts the certificate on 4443, both LAN and WAN-address requests on 443 return
only the fixed-port redirect, and Cloudflare-tagged requests on 4443 receive 403.
Keep the direct IP available throughout. Recheck login/redirect behavior after
access or firmware changes, including the nonstandard external port.

Grafana reads the provisioned dashboard JSON automatically. Validate the generated
exporter config and run `promtool check config` against the final Prometheus
config. Check `up{job="qnap-snmp",instance="qnap-nas"}` and each dashboard query
against real samples, including gaps on failed collection. Keep the existing
Prometheus and Grafana data volumes intact. If reloading Prometheus manually,
send HUP inside the container as documented in
[`prometheus/AGENTS.md`](../prometheus/AGENTS.md); the HTTP lifecycle endpoint is
disabled. For the later widget activation, run a least-privilege login test
without printing credentials, cookies or returned session IDs.

To roll back SNMP collection, remove the `qnap-snmp` scrape job through a PR and
stop the exporter through the deployment workflow. Remove its credentials and
disable the NAS's SNMP service when no collector needs it. Preserve the access
route, Homepage NAS link and stored Prometheus history. Reverting access itself
is a separate change: remove the NAS proxy configuration and gracefully reload
SWAG. These monitoring changes do not alter NAS storage or the DHCP reservation.

References: [Homepage QNAP widget](https://gethomepage.dev/widgets/services/qnap/),
[Homepage environment secrets](https://gethomepage.dev/installation/docker/#using-environment-secrets),
[community dashboard 9330](https://grafana.com/grafana/dashboards/9330-qnap-snmp/),
[QuTS hero SNMP settings](https://docs.qnap.com/operating-system/quts-hero/6.0.x/en-us/configuring-snmp-settings-42DBF952.html),
[delegated administration](https://docs.qnap.com/operating-system/quts-hero/6.0.x/en-us/delegated-administration-87EDB7A6.html).
