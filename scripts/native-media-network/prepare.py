#!/usr/bin/env python3
"""Prepare a private native Compose candidate without touching running services."""

import argparse
import copy
import json
import os
from pathlib import Path


MEDIA = {"plex", "channels-dvr"}


def add_hosts(service, address):
    """Preserve unrelated host aliases and reject conflicting media aliases."""
    existing = service.get("extra_hosts", {})
    if isinstance(existing, list):
        hosts = {}
        for entry in existing:
            name, separator, value = entry.partition("=")
            if not separator:
                name, separator, value = entry.partition(":")
            if not separator or not name or not value or name in hosts:
                raise ValueError("Invalid or duplicate extra_hosts entry")
            hosts[name] = value
    elif isinstance(existing, dict):
        hosts = copy.deepcopy(existing)
    else:
        raise ValueError("extra_hosts must be a list or mapping")
    for name in sorted(MEDIA):
        if name in hosts and hosts[name] not in (address, [address]):
            raise ValueError(f"Conflicting host alias: {name}")
        hosts[name] = address
    service["extra_hosts"] = hosts


def prepare(document, service_name):
    """Change only the selected service's network fields in an audited native input."""
    result = copy.deepcopy(document)
    service = result["services"][service_name]
    if service.get("container_name") != service_name:
        raise ValueError("Select the actual container service, not a database dependency")
    # A compiled native input must have fully resolved storage and environment.
    for item in service.get("volumes", []):
        if not isinstance(item, dict):
            raise ValueError("Use normalized docker compose config --format json input")
        if item.get("type") == "bind":
            source = item.get("source", "")
            if not source.startswith("/") or source.startswith(("/mnt/c/", "/mnt/e/", "/usr/lib/wsl/")):
                raise ValueError("Use the accepted native storage configuration first")
    if service.get("env_file"):
        raise ValueError("Resolve env_file into a protected compiled input first")
    if service_name in MEDIA:
        mode = service.get("network_mode")
        networks = service.get("networks", {})
        if mode not in (None, "host") or set(networks) - {"proxynet"}:
            raise ValueError("Unexpected media network configuration")
        service.pop("ports", None)
        service.pop("networks", None)
        service["network_mode"] = "host"
        # Host-networked apps no longer use Docker's embedded DNS.
        add_hosts(service, "127.0.0.1")
    else:
        if service.get("network_mode") or "proxynet" not in service.get("networks", {}):
            raise ValueError("Consumers must retain their proxynet attachment")
        add_hosts(service, "host-gateway")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--service", required=True)
    args = parser.parse_args()
    result = prepare(json.loads(args.input.read_text()), args.service)
    # Compiled inputs contain secrets. Do not print them or overwrite rollback inputs.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
