# QNAP access and monitoring

The TS-664 runs QuTS hero at the reserved address `192.168.50.91` on its 10GbE
interface. The RAID5 pool holds Media and Recovery.

## Private access

- Normal bookmark: <https://nas.benlawson.dev/>, redirecting to the private
  <https://nas.benlawson.dev:4443/> listener through SWAG.
- Direct fallback: <http://192.168.50.91:8080/>.
- The hostname resolves to the server at `192.168.50.40`. SWAG binds the NAS
  listener only to `192.168.50.40:4443`; public port 443 only redirects this
  hostname. Do not forward 4443 on the router or add a NAS Cloudflare Tunnel route.
- The private listener rejects Cloudflare-tagged requests. Preserve the dedicated
  listener and router boundary when changing proxy configuration.

After access or firmware changes, verify HTTPS login/logout, hostname redirects
and UI WebSockets. Update proxy and monitoring URLs together if NAS ports change.
Validate Nginx with `docker exec swag nginx -t` before a graceful reload.

## Metrics and alerts

The [SNMP collector runbook](../snmp-exporter/README.md) owns SNMPv3 credentials,
MIB generation, physical drive identities, storage units and collection checks.
Prometheus scrapes `qnap-snmp` with `instance="qnap-nas"` every 60 seconds.
The [QNAP dashboard](https://grafana.benlawson.dev/d/qnap-nas) and existing Grafana
channels provide storage monitoring and alerts as code.

Keep physical ZFS pool allocation separate from thin shared-folder quotas.
Missing or unsupported sensors remain unknown; a successful scrape alone does
not prove storage health. Recheck units and drive mappings after firmware or
hardware changes. Preserve the existing Prometheus history and Grafana volumes.

## Homepage statistics

Homepage uses a dedicated non-administrator **System Monitoring** account. Its
Media, Public and Recovery share access and file-access applications are denied.
`HOMEPAGE_VAR_QNAP_USERNAME` and `HOMEPAGE_VAR_QNAP_PASSWORD` belong only in
`homepage/.env.secret`, encrypted by git-crypt. Do not use the interactive admin
account or print credentials/session IDs during a login test.

The widget uses the existing private HTTPS route and verified TLS certificate.
It shows CPU, memory and system temperature. Storage remains in Grafana because
the widget aggregates shared-folder quotas instead of physical pool allocation.
Its system and volume API permission checks must both continue to pass after a
firmware or widget update, even when storage fields are not displayed.

Changing the two environment variables requires an admitted Homepage deployment.
Removing the widget must preserve the NAS link, availability check and SNMP
collection. Remove the dedicated account only after its consumers are gone.
