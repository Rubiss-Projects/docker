#!/usr/bin/env python3
"""Prioritize Tracearr in the existing Windows Docker recovery/maintenance order.

Dry run by default. --apply backs up the shared helper before updating its
noncritical WSL repair order. Scheduled tasks, critical startup and locks stay intact.
"""

import argparse
import datetime as dt
from pathlib import Path
import re


def update_order(text):
    pattern = r'(?ms)^\$DockerWslBindRepairOrder = @\(\n(.*?)^\)'
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError('Expected one WSL repair order; inspect the Windows helper')
    match = matches[0]
    block = match.group(1)
    names = re.findall(r'^\s*"([\w-]+)"\s*,?\s*$', block, re.M)
    if names[:4] != ['socket-proxy', 'uptime-kuma', 'plex', 'swag']:
        raise ValueError('Critical startup order changed; inspect the Windows helper')
    if 'tracearr' in names:
        if names.count('tracearr') != 1 or names.index('tracearr') != 4:
            raise ValueError('Tracearr already has a different priority; inspect the Windows helper')
        return text
    anchor = '    "swag",\n'
    if block.count(anchor) != 1:
        raise ValueError('Expected one SWAG entry; inspect the Windows helper')
    updated = block.replace(anchor, anchor + '    "tracearr",\n', 1)
    return text[:match.start(1)] + updated + text[match.end(1):]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--scripts-dir', type=Path, default=Path('/mnt/e/Scripts'))
    args = parser.parse_args()
    path = args.scripts_dir / 'docker-desktop-common.ps1'
    original = path.read_text()
    updated = update_order(original)
    if updated == original:
        print('Tracearr maintenance priority already installed')
        return
    if args.apply:
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        path.with_name(path.name + '.before-tracearr-' + stamp).write_bytes(path.read_bytes())
        path.write_text(updated)
    print(('Updated ' if args.apply else 'Would update ') + str(path))


if __name__ == '__main__':
    main()
