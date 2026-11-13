# Secondary DNS

BEN-SERVER serves filtered DNS at `192.168.50.40:53` (TCP and UDP), with a
admin UI at `https://dns-secondary.benlawson.dev/admin/` through SWAG, matching
the primary Pi-hole proxy. Direct LAN access at `http://192.168.50.40:8088/admin/`
remains available for proxy troubleshooting. The existing Pi at
`192.168.50.216` remains the configuration source. DHCP stays on the router.

Deploy through the native adapter after admitting both `pihole-secondary` and
`nebula-sync`. Keep `/etc/pihole` on local storage. Preserve Ubuntu's loopback
DNS listeners by publishing only the explicit LAN address. No router port
forwarding changes are needed; the HTTPS route uses the existing wildcard
certificate and the Pi-hole login. The sync helper is monitored in Kuma and
does not have a Homepage tile.

Nebula Sync runs at startup and hourly at minute 17. It copies DNS upstreams,
local records, conditional forwarding, DNSSEC, blocking settings, lists, groups,
clients and their associations. It never copies DHCP, interface or web settings.
The tracked Blitz/Overwolf dnsmasq rules are mounted separately. Make filtering
changes on the Pi; replica edits can be overwritten at the next sync. Each
resolver queries its own upstreams and can run while the other is unavailable.

Nebula's `RUN_GRAVITY` is disabled because it rebuilds the primary as well as
replicas. After adding/changing adlist sources, rebuild gravity on the secondary
through the native adapter (`exec -T pihole-secondary pihole -g`); otherwise its
built-in scheduled gravity update applies those source changes. Domain exceptions
and groups synchronize hourly. Initial deployment must rebuild secondary gravity
after the first successful sync. Sync success/failure is reported to a Kuma push
monitor, with a two-hour missing-heartbeat threshold.

Secrets are encrypted `.env.secret` overlays: `PIHOLE_PASSWORD` for the replica,
and `PRIMARY`/`REPLICAS` API credentials for Nebula Sync. Never print these or
expanded Compose recipes. Update the replica credential in both overlays together.

## Router cutover

On November 13, the ASUS router's LAN DHCP was changed to advertise
`192.168.50.216` and `192.168.50.40`. The additional router DNS advertisement is
disabled. Router IPv6 is disabled; IP reservations and the 86400-second lease
time were preserved. The Windows Ethernet client received exactly this DNS pair
after lease renewal. Other DHCP clients adopt it when renewing their leases;
reconnect them if immediate cutover is needed. Manually configured devices and
application-level encrypted DNS require separate auditing.

Windows resolution and blocking passed with either Pi-hole temporarily stopped,
one at a time. Both were restored, with timed recovery safeguards during testing.
BEN-SERVER's explicit Ethernet DNS pair is managed by
`scripts/native-host-network/90-native-dns.yaml`.

For subsequent maintenance, query each address explicitly for a public name, a blocked name,
`ads.overwolf.com`, and `grafana.benlawson.dev`, using UDP and TCP. Confirm the
last sync succeeded and both admin interfaces work. After cutover, test failure
of each resolver only during an approved maintenance window. DNS clients may
query either server and may wait for timeouts; this is not instantaneous failover.

To back out before cutover, stop only the two new stacks through the native
adapter; retain their data. After cutover, remove the secondary from DHCP before
decommissioning it. Do not stop the original Pi-hole or restart Docker/SWAG.
