#!/usr/bin/env python3
"""Render the narrow INPUT guard required before starting native media listeners."""

import argparse
import ipaddress
import re
from pathlib import Path


def interface(value):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", value):
        raise ValueError("Invalid interface name")
    return value


def render(lan_interface, lan_networks, bridge_interface, bridge_network):
    lan_interface = interface(lan_interface)
    bridge_interface = interface(bridge_interface)
    networks = [ipaddress.ip_network(value, strict=True) for value in lan_networks]
    bridge = ipaddress.ip_network(bridge_network, strict=True)
    if bridge.version != 4 or not bridge.is_private:
        raise ValueError("Expected a private IPv4 proxynet subnet")
    if not networks or any(not network.is_private or network.prefixlen == 0 for network in networks):
        raise ValueError("Provide explicit private LAN prefixes")
    trust = ['        iifname "lo" accept', '        iifname "tailscale0" accept']
    trust += [f'        iifname "{lan_interface}" {"ip" if n.version == 4 else "ip6"} saddr {n} accept' for n in networks]
    trust += [f'        iifname "{bridge_interface}" ip saddr {bridge} accept', "        counter drop"]
    # One nft transaction replaces only this owned table; Docker/Tailscale stay intact.
    return '\n'.join([
        "add table inet native_media",
        "flush table inet native_media",
        "table inet native_media {",
        "    chain trusted_clients {", *trust, "    }",
        "    chain input {",
        "        type filter hook input priority -10; policy accept;",
        "        tcp dport { 3005, 8089, 8324, 32469 } jump trusted_clients",
        "        udp dport { 1900, 1901, 5353, 32410, 32412, 32413, 32414, 65001 } jump trusted_clients",
        "    }", "}", "",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lan-interface", required=True)
    parser.add_argument("--lan-network", action="append", required=True)
    parser.add_argument("--bridge-interface", required=True)
    parser.add_argument("--bridge-network", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rules = render(args.lan_interface, args.lan_network, args.bridge_interface, args.bridge_network)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(rules)


if __name__ == "__main__":
    main()
