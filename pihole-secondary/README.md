# Secondary DNS

BEN-SERVER serves filtered DNS at `192.168.50.40:53` (TCP and UDP), with a
LAN-only admin UI at `http://192.168.50.40:8088/admin/`. The existing Pi at
`192.168.50.216` remains the configuration source. DHCP stays on the router.

Deploy through the native adapter after admitting both `pihole-secondary` and
`nebula-sync`. Keep `/etc/pihole` on local storage. Preserve Ubuntu's loopback
DNS listeners by publishing only the explicit LAN address. No router port
forwarding or public web route is needed.

Nebula Sync runs at startup and hourly at minute 17. It copies DNS upstreams,
local records, conditional forwarding, DNSSEC, blocking settings, lists, groups,
clients and their associations. It never copies DHCP, interface or web settings.
The tracked Blitz/Overwolf dnsmasq rules are mounted separately. Make filtering
changes on the Pi; replica edits can be overwritten at the next sync. Each
resolver queries its own upstreams and can run while the other is unavailable.

Secrets are encrypted `.env.secret` overlays: `PIHOLE_PASSWORD` for the replica,
and `PRIMARY`/`REPLICAS` API credentials for Nebula Sync. Never print these or
expanded Compose recipes. Update the replica credential in both overlays together.

## Deferred cutover

Do not change the router until a restart window is approved. Then configure LAN
DHCP to advertise `192.168.50.216` and `192.168.50.40`, review IPv6 DNS advertisements,
and remove public/router DNS alternatives from clients that require filtering.
Audit manually configured clients separately, including BEN-SERVER's startup
resolver needs. Renew client leases after the router change.

Before cutover, query each address explicitly for a public name, a blocked name,
`ads.overwolf.com`, and `grafana.benlawson.dev`, using UDP and TCP. Confirm the
last sync succeeded and both admin interfaces work. After cutover, test failure
of each resolver only during an approved maintenance window. DNS clients may
query either server and may wait for timeouts; this is not instantaneous failover.

To back out before cutover, stop only the two new stacks through the native
adapter; retain their data. After cutover, remove the secondary from DHCP before
decommissioning it. Do not stop the original Pi-hole or restart Docker/SWAG.
