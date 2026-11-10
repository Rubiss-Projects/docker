# Native media networking

Plex and Channels DVR use the Linux host network after the native storage
migration. Direct clients then reach the applications without Docker NAT, with
their peer addresses and LAN discovery intact. This replaces the Windows/WSL
Caddy workaround once direct routing is accepted. A reverse proxy remains a
proxy even when its upstream uses host networking.

These helpers prepare **network-only** changes to accepted native compiled
Compose JSON. They do not install, restart containers, change application
preferences, edit router rules, or retire Caddy. They are intentionally outside
the Windows deployment path. Automatic native deployment must stay held until
it can reproduce both the accepted storage and networking configuration.

## Prepare candidates

Run on native Linux, using the protected compiled file named in each running
container's `com.docker.compose.project.config_files` label. Do not compile the
Windows base Compose file as a replacement: it still contains WSL mounts.
Retain that original input and a fresh `docker inspect` as rollback evidence.

```sh
sudo install -d -m 700 /var/lib/native-media-network
sudo python3 scripts/native-media-network/prepare.py /path/to/accepted/plex-compiled.json /var/lib/native-media-network/plex.json --service plex
sudo docker compose -f /var/lib/native-media-network/plex.json config --quiet
```

Do the same for `channels-dvr`. The helper preserves the project, pinned image,
volumes (including subpaths and streaming sessions), secrets, GPU reservation,
CPU affinity and every non-network field. It removes published ports and the
media service's bridge attachment, sets `network_mode: host`, and adds loopback
aliases for communication between the two host-networked applications.

For each **confirmed consumer**, prepare its existing compiled input with its
own service name. This adds `plex=host-gateway` and
`channels-dvr=host-gateway` without changing its networks or dependency services.
Homepage, Uptime Kuma, SWAG and Tracearr are consumers; also inspect Sonarr,
Radarr, Seerr, Channels integration settings and other stored application URLs.
Runtime labels/environment alone are not a complete dependency inventory.
The aliases retain existing URLs and monitor IDs; they do not bypass application
authentication. Check container-to-host connectivity before relying on them.
SWAG's variable upstream resolver may need an explicit native host address:
nginx's Docker DNS resolver does **not** consult `/etc/hosts` for variable
`proxy_pass` names. Verify or retarget the Channels upstream separately.

Outputs contain resolved secrets, are created with mode 0600, and refuse to
overwrite existing files. Do not commit them, print `compose config`, or use
`down -v`. Preparation does not prove the input matches the running container;
compare image, mounts, environment, labels and resource settings before applying.

## Guard host listeners first

Host-network traffic uses INPUT, not Docker's published-port forwarding chains.
Capture the current rules/listeners and derive the actual physical interface,
LAN IPv4/IPv6 prefixes, proxynet subnet and bridge interface from the host.

```sh
python3 scripts/native-media-network/firewall.py --lan-interface eno1 --lan-network 192.168.50.0/24 --lan-network fd00::/64 --lan-network fe80::/64 --bridge-interface br-example --bridge-network 172.30.0.0/16 --output /tmp/native-media.nft
sudo nft --check -f /tmp/native-media.nft
sudo install -m 600 /tmp/native-media.nft /etc/nas-migration/native-media.nft
sudo install -m 644 scripts/native-media-network/native-media-firewall.service /etc/systemd/system/native-media-firewall.service
sudo systemctl daemon-reload
sudo systemctl enable --now native-media-firewall.service
sudo nft list table inet native_media
```

Substitute observed values; the example IPv6 prefix is not a deployment default.
The single atomic transaction replaces only the owned `inet native_media` table.
It restricts Channels TCP 8089 and media control/discovery ports to loopback,
the specified LAN prefixes on the physical interface, proxynet on its bridge,
and Tailscale. It covers IPv4 and IPv6, leaves SSH and other services alone, and
leaves authenticated Plex TCP 32400 available for the intended direct route.
It does not protect arbitrary application-configured additional listener ports:
inspect the actual namespace listeners before and after changing networks.
Existing Docker FORWARD rules continue to govern bridge services.

Enabling the unit makes Docker require it on future starts; a missing/invalid
rules file prevents Docker startup. This does not restart Docker now. Keep the
guard enabled as long as either app uses host networking. After recreating
proxynet, regenerate/check/reload the rules with the new bridge interface before
depending on its access. Never flush the global nftables ruleset or reload a
distribution firewall configuration that would erase Docker/Tailscale rules.

## Controlled cutover and acceptance

1. Verify current recovery evidence, accepted native mount guards, exact input
   drift, port ownership, Plex sessions and Channels clients/recording activity.
   Use a scoped maintenance window without replacing monitors or their history.
2. Install/verify the media firewall. Prepare consumers and retarget SWAG's
   Channels upstream as needed. Keep Caddy and its certificate timer available.
3. Gracefully recreate Plex first to release its old published discovery ports,
   then Channels, preserving the existing project and service names. Use each
   candidate with `up -d --no-deps --pull never SERVICE`; never start database
   dependencies, stopped stacks or a duplicate application identity. Apply only
   confirmed consumer services, likewise with `--no-deps`.
4. Verify actual host mode, exact mounts/images/GPU/CPU limits, both applications'
   readiness, LAN peer addresses, authentication, discovery and normal playback/
   recording behavior. Verify Homepage, Tracearr, the proxy and the **existing**
   Kuma monitors. Check untrusted IPv4/IPv6 denial and trusted bridge/LAN access.
5. For Plex, explicitly replace the router's Caddy mapping with public TCP 18443
   to native TCP 32400; restore normal Plex publication with manual external port
   18443 and its certificate-backed `plex.direct` endpoint. Remove the Caddy custom
   URL only after the secure direct route is accepted. Preserve authentication,
   TLS, Relay and bandwidth settings unless a reviewed correction is necessary.
   Do not classify WAN clients as LAN or trust arbitrary forwarded headers.
6. Retire the media Caddy service, private Channels relay, certificate-copy timer
   and their monitoring only when no accepted route depends on them. Retain
   recoverable configuration and document the final direct endpoints. The
   separate temporary gaming-PC web/T3 transit has its own routing cutover.

Channels Away From Home is deferred by the owner. Do not expose its administration
port or add a new remote-access acceptance gate during this cutover.

If acceptance fails, gracefully restore the exact saved Compose inputs for the
affected services and the saved router/Plex publication settings. Keep Caddy
available until that transition is verified. Restore networking, not older
application data: services may have written new state since their backups.
Remove this firewall only after all host-networked media listeners are stopped
or restored to their accepted bridge configuration.

## Validation

```sh
python3 -m unittest discover -s scripts/native-media-network -p 'test_*.py'
```

Running the same command with `sudo` on Linux with `ip`, `nft`, `nsenter` and
`unshare` also tests trusted/untrusted IPv4 and IPv6 TCP connections in isolated
namespaces. It verifies Channels denial and Plex reachability without touching
production interfaces or rules.

Also validate prepared JSON with the actual native Compose version and check
the generated firewall with native nftables before applying it. Preparation and
unit tests alone do not demonstrate a completed production cutover.

References: [Docker host networking](https://docs.docker.com/engine/network/drivers/host/),
[Compose extra_hosts](https://docs.docker.com/reference/compose-file/services/#extra_hosts),
[atomic nftables updates](https://wiki.nftables.org/wiki-nftables/index.php/Atomic_rule_replacement).
