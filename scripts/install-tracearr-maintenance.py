#!/usr/bin/env python3
"""Prioritize Tracearr in the existing Windows Docker recovery/maintenance order.

Dry run by default. --apply backs up the shared helper before updating its
noncritical WSL repair order. Scheduled tasks, critical startup and locks stay intact.
"""

import argparse
import datetime as dt
from pathlib import Path
import re
import os
import tempfile


def atomic_write(path, text):
    """Keep the old helper readable until its complete replacement is ready."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix=path.name + '.',
                                         suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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


def update_sentinel(text):
    """Replace the retired monitor's persistence check with Tracearr checks."""
    old = '''if is_running tautulli; then
  check tautulli docker exec tautulli sh -lc 'test $(stat -c%s /config/tautulli.db) -gt 1000000 && test -f /config/config.ini'
fi'''
    new = '''if is_running tracearr; then
  check tracearr docker exec tracearr node -e 'fetch("http://127.0.0.1:3000/health").then(r=>r.json()).then(x=>process.exit(x.mode === "ready" && x.db && x.redis ? 0 : 1)).catch(()=>process.exit(1))'
  check tracearr-history sh -lc "docker exec tracearr-db psql -U tracearr -d tracearr -Atc 'SELECT EXISTS (SELECT 1 FROM sessions LIMIT 1);' | grep -qx t"
fi'''
    if new in text and old not in text:
        return text
    if text.count(old) != 1:
        raise ValueError('Stateful sentinel changed; inspect it before replacing the retired service check')
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--scripts-dir', type=Path, default=Path('/mnt/e/Scripts'))
    args = parser.parse_args()
    changes = []
    for name, transform in [('docker-desktop-common.ps1', update_order),
                            ('docker-stateful-sentinel-check.sh', update_sentinel)]:
        path = args.scripts_dir / name
        original = path.read_text()
        updated = transform(original)
        if updated != original:
            changes.append((path, updated))
    for path, updated in changes:
        if args.apply:
            stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            path.with_name(path.name + '.before-tracearr-' + stamp).write_bytes(path.read_bytes())
            atomic_write(path, updated)
        print(('Updated ' if args.apply else 'Would update ') + str(path))
    if not changes:
        print('Tracearr maintenance priority and stateful checks already installed')


if __name__ == '__main__':
    main()
