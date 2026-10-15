# QNAP access and monitoring

The TS-664 runs QuTS hero h6.0.2 at the router-reserved address
`192.168.50.91`. It is currently diskless and uninitialized. The HTTPS route and
Homepage availability card work at this stage; authenticated statistics and SNMP
collection require NAS initialization after drive installation.

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

After initialization, verify login and logout through HTTPS, redirects remaining
on the hostname, and any WebSocket connections used by the NAS UI. The diskless
setup page is not a complete test of the eventual management interface. If the
NAS HTTP/HTTPS ports change, update the proxy and monitoring URLs in the same PR.
The planned 10GbE card changes the reservation's MAC, not the NAS's `.91` address.

## Available before the drives arrive

- Homepage Hardware contains a NAS link and HTTP reachability indicator. A green
  indicator means the web endpoint responds, not that storage is healthy.
- Grafana's [QNAP NAS dashboard](https://grafana.benlawson.dev/d/qnap-nas) is
  provisioned with collection pending. It must not display missing metrics as
  zero usage or healthy drives.
- SNMP collector and scrape inputs are staged under
  [`prometheus/staged/qnap`](../prometheus/staged/qnap/). They are not loaded into
  Prometheus. No monitoring accounts, guessed credentials or failing targets
  are created while the NAS is uninitialized.

## Activation handoff after drive installation

Follow the [physical setup and drive qualification plan](https://nas-linux-migration-field-guide-2026.rubiss89.chatgpt.site/physical-setup)
first. Monitoring does not authorize initialization, erasure or pool creation.
Reconcile drive identities and the approved test sequence before those actions.

1. Once QuTS hero is initialized according to that sequence, enable its built-in
   SNMPv3 with authentication and privacy. Use dedicated monitoring credentials,
   keep UDP 161 on the LAN, and restrict the source to the observed monitoring
   host address if the NAS provides an access restriction.
2. Download the MIB from this NAS. Follow the staged collector instructions to
   generate and validate the exporter configuration. Deploy the pinned exporter
   on Ben-server's `proxynet` without a published port, with encrypted secrets,
   Dependabot coverage and a reviewed Prometheus scrape configuration.
3. Before long drive qualification, compare CPU/system/disk temperatures and
   drive/bay labels with the NAS interface. Check that all installed drives appear.
   Unsupported OIDs stay absent; do not substitute zeroes. Recording temperatures
   is useful during testing but is not a substitute for SMART and surface tests.
4. After the accepted drives form the production RAID5 pool, compare capacity and
   usage panels against QuTS hero. Validate bytes versus display units, pool
   versus shared-folder/volume semantics, snapshots and reservations. Only then
   enable the Homepage widget and storage panels that agree with the NAS.
5. Verify the end-to-end readings in Homepage, Prometheus and Grafana before the
   media copy. Keep this integration observational; it adds no restarts, shutdown
   actions or new alerts.

## Homepage widget activation

Create a dedicated local account, initially with the **System Monitoring**
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
fields does not eliminate the widget's volume API request, so do not enable it
against the diskless setup wizard. Update the card description once active.

## Validation and rollback

Validate Nginx with `docker exec swag nginx -t` before a graceful reload. The
initial additional port mapping requires recreating only the SWAG container;
subsequent config-only updates can use a graceful reload. Verify the browser
trusts the certificate on 4443, both LAN and WAN-address requests on 443 return
only the fixed-port redirect, and Cloudflare-tagged requests on 4443 receive 403.
Keep the direct IP available throughout. Recheck login/redirect behavior after
initialization, including the nonstandard external port.

Grafana reads the provisioned dashboard JSON automatically. Before activating
collection, validate the generated exporter config and run `promtool check config`
against the final Prometheus config; check `up{job="qnap-snmp"}` and the individual
queries against real samples. Run a least-privilege widget login test without
printing credentials, cookies or returned session IDs.

Rollback through a PR: remove the NAS route/card and dashboard, or remove the
scrape target and widget block if reverting only the later activation. Reload
SWAG gracefully after route removal. NAS storage, services and the DHCP
reservation are unaffected.

References: [Homepage QNAP widget](https://gethomepage.dev/widgets/services/qnap/),
[Homepage environment secrets](https://gethomepage.dev/installation/docker/#using-environment-secrets),
[community dashboard 9330](https://grafana.com/grafana/dashboards/9330-qnap-snmp/),
[QuTS hero SNMP settings](https://docs.qnap.com/operating-system/quts-hero/6.0.x/en-us/configuring-snmp-settings-42DBF952.html),
[delegated administration](https://docs.qnap.com/operating-system/quts-hero/6.0.x/en-us/delegated-administration-87EDB7A6.html).
