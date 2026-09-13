#!/usr/bin/env python3
"""Install Grafana hooks in the existing Windows Docker maintenance tasks.

Default is a dry run. --apply backs up and updates only the shared helper and
nightly script; scheduled task definitions, enabled states, and locks are unchanged.
"""

import argparse
import datetime as dt
from pathlib import Path


def replace_once(text, old, new):
    if new in text:
        return text
    if text.count(old) != 1:
        raise ValueError("Windows maintenance script changed; inspect it before installing hooks")
    return text.replace(old, new, 1)


def common_hooks(text):
    text = replace_once(text,
        '# Shared Docker Desktop maintenance helpers.\n',
        '# Shared Docker Desktop maintenance helpers.\n. "E:\\Docker\\scripts\\grafana-maintenance.ps1"\n')
    start = text.index('function Start-UptimeKumaMaintenance {')
    end = text.index('function Stop-UptimeKumaMaintenance {')
    block = text[start:end]
    block = replace_once(block,
        '    Write-DockerLog "Creating Uptime Kuma maintenance window for Docker Desktop maintenance."',
        '    $grafanaStarted = Start-GrafanaMaintenance -TtlMinutes $TtlMinutes -Reason $Reason\n\n'
        '    Write-DockerLog "Creating Uptime Kuma maintenance window for Docker Desktop maintenance."')
    # A successfully created Grafana silence still needs cleanup if Kuma was down.
    block = block.replace('return $false', 'return $grafanaStarted')
    text = text[:start] + block + text[end:]
    return replace_once(text,
        'function Stop-UptimeKumaMaintenance {\n',
        'function Stop-UptimeKumaMaintenance {\n    Stop-GrafanaMaintenance\n')


def nightly_hooks(text):
    return replace_once(text,
        '} finally {\n    Remove-Item -Path $DockerMaintenanceLockPath',
        '} finally {\n    Stop-GrafanaMaintenance\n    Remove-Item -Path $DockerMaintenanceLockPath')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--scripts-dir', type=Path, default=Path('/mnt/e/Scripts'))
    args = parser.parse_args()
    updates = []
    for name, transform in [('docker-desktop-common.ps1', common_hooks), ('docker-desktop-nightly-maintenance.ps1', nightly_hooks)]:
        path = args.scripts_dir / name
        original = path.read_text()
        updated = transform(original)
        if original != updated:
            updates.append((path, updated))
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for path, updated in updates:
        if args.apply:
            backup = path.with_name(path.name + '.before-grafana-' + stamp)
            backup.write_bytes(path.read_bytes())
            path.write_text(updated)
        print(('Updated ' if args.apply else 'Would update ') + str(path))
    if not updates:
        print('Grafana maintenance hooks already installed')


if __name__ == '__main__':
    main()
