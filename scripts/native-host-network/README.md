# Native host DNS

`90-native-dns.yaml` supplements the installer's existing Netplan configuration
on BEN-SERVER. Keep DHCP addressing, routes, interface names and Tailscale's
separate DNS configuration unchanged. Only Ethernet DNS is overridden: Pi-hole
at `192.168.50.216`, with the secondary at `192.168.50.40`. DHCP and IPv6 router
advertisements must not add the router's inconsistent DNS server again.

The November 13 cutover replaces the temporary Google fallback with the second
Pi-hole. The Pi remains available while BEN-SERVER boots and Docker starts;
both Pi-hole containers use independent external upstreams. Tailscale's resolver
configuration remains separate. Do not point either Pi-hole upstream at the other.

On November 11 the host selected `192.168.50.1` from its DHCP DNS list. That
resolver returned no address for `grafana.benlawson.dev`; both configured
resolvers returned `192.168.50.40`. Uptime Kuma reported DNS failures while all
50 containers retained their start times. Updating the live Ethernet resolver
list restored all 45 monitors without restarting applications.

Before installation, copy the host's existing `/lib/netplan`, `/etc/netplan`
and `/run/netplan` YAML files into matching directories under a temporary root,
add this file under its `etc/netplan`, and run:

```sh
netplan generate --root-dir /path/to/temporary-root
```

Inspect the generated `run/systemd/network/*enp3s0.network`: it must retain
DHCP addressing and contain only the two intended DNS addresses, with DNS from
DHCP and router advertisements disabled. This validation does not apply the
configuration to the live interface.

After review, install the file as root with mode 0600:

```sh
install -o root -g root -m 0600 scripts/native-host-network/90-native-dns.yaml /etc/netplan/90-native-dns.yaml
```

Apply the current pair to the running Ethernet link without restarting networking:

```sh
resolvectl dns enp3s0 192.168.50.216 192.168.50.40
resolvectl flush-caches
```

Generate the production backend configuration after installation, without
applying it or restarting networking. Netplan also generates it at boot. The
runtime resolver setting covers the current session; the installed YAML and
generated backend configuration preserve it across future network setup.
Verify host and Uptime Kuma resolution and monitor health after installation.

See the [Netplan YAML reference](https://netplan.readthedocs.io/en/stable/netplan-yaml/)
and [generate reference](https://netplan.readthedocs.io/en/stable/netplan-generate/).
