#!/usr/bin/env python3
"""Install native read-only Transmission probes into an existing Linux Telegraf service."""
import argparse
import datetime
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent
CONFIG = Path('/etc/telegraf/telegraf.conf')
CONFIG_DIR = Path('/etc/telegraf/telegraf.d')
CREDENTIALS = Path('/etc/telegraf/transmission-rpc-credentials.json')
LIB = Path('/usr/local/lib/transmission')
BACKUP_ROOT = Path('/var/backups/transmission-telegraf')


def atomic_write(path, data, mode, gid=0):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        out.write(data)
    try:
        os.chown(temporary, 0, gid)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Install after validation; default only checks prerequisites')
    args = parser.parse_args()
    if sys.platform != 'linux' or 'microsoft' in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Use this installer on native Linux, not Windows or WSL.')
    if os.geteuid() != 0:
        raise SystemExit('Run as root so the private existing configuration can be checked.')
    account = pwd.getpwnam('telegraf')
    assert shutil.which('telegraf'), 'Install the signed Telegraf package first; see NATIVE-MONITORING.md'
    assert CONFIG.is_file() and not CONFIG.is_symlink()
    existing = tomllib.loads(CONFIG.read_text())
    assert existing.get('outputs'), 'The existing authenticated output must already be configured'
    assert not existing.get('inputs', {}).get('win_perf_counters'), 'Port Windows counters before native installation'
    assert {'cpu', 'mem', 'disk', 'system'} <= set(existing.get('inputs', {})), 'Keep native host inputs enabled'
    for item in existing.get('inputs', {}).get('exec', []):
        assert not any('transmission' in str(command).lower() for command in item.get('commands', [])), 'Move existing Transmission inputs out of the base config before installing the managed fragment'
    for item in existing.get('inputs', {}).get('http_response', []):
        assert 'http://127.0.0.1:9091/transmission/rpc' not in item.get('urls', []), 'The managed fragment owns the Transmission endpoint input'
    assert CREDENTIALS.is_file() and not CREDENTIALS.is_symlink(), 'Stage the existing USER/PASS JSON privately; never pass credentials as arguments'
    info = CREDENTIALS.stat()
    assert info.st_uid == 0 and not info.st_mode & 0o027, 'Credentials must be root owned, not writable by other accounts, and not readable by everyone'
    credentials = json.loads(CREDENTIALS.read_text())
    assert set(credentials) == {'USER', 'PASS'} and all(isinstance(v, str) and '\x00' not in v for v in credentials.values())
    command = subprocess.check_output(['systemctl', 'show', 'telegraf.service', '-p', 'ExecStart', '--value'], text=True)
    assert re.search(r'--?config-directory(?:=|\s+)/etc/telegraf/telegraf\.d(?:\s|;|$)', command), 'The installed service must load the managed fragment directory'
    active = subprocess.run(['systemctl', 'is-active', '--quiet', 'telegraf.service']).returncode == 0
    assert active, 'Start and verify the existing native collector first'
    targets = {
        LIB / 'rpc-health.py': ((ROOT / 'scripts/rpc-health.py').read_bytes(), 0o755, 0),
        LIB / 'native-host-rpc.py': ((ROOT / 'scripts/native-host-rpc.py').read_bytes(), 0o755, 0),
        CONFIG_DIR / 'transmission-native.conf': ((ROOT / 'telegraf-native.conf').read_bytes(), 0o640, account.pw_gid),
    }
    for directory in [LIB, CONFIG_DIR]:
        if directory.exists():
            info = directory.stat()
            assert not directory.is_symlink() and info.st_uid == 0 and not info.st_mode & 0o022
    for target in targets:
        if target.exists():
            assert target.is_file() and not target.is_symlink() and target.stat().st_uid == 0
    changed = {p: value for p, value in targets.items() if not p.exists() or p.read_bytes() != value[0] or stat.S_IMODE(p.stat().st_mode) != value[1] or p.stat().st_gid != value[2]}
    credential_permissions_changed = stat.S_IMODE(CREDENTIALS.stat().st_mode) != 0o640 or CREDENTIALS.stat().st_gid != account.pw_gid
    if not args.apply:
        print(json.dumps({'prerequisitesPassed': True, 'filesToUpdate': [str(p) for p in changed], 'applyRequested': False}))
        return
    if not changed and not credential_permissions_changed:
        print('Native Transmission metrics are already installed; no collector restart needed.')
        return
    backup = BACKUP_ROOT / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    originals = {}
    for path in changed:
        originals[path] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode), path.stat().st_gid) if path.exists() else None
        if path.exists():
            shutil.copy2(path, backup / path.name)
    credential_info = CREDENTIALS.stat()
    restart_attempted = False
    try:
        for directory in [LIB, CONFIG_DIR]:
            if not directory.exists():
                directory.mkdir(mode=0o755)
                # A private root umask must not prevent service-user traversal.
                directory.chmod(0o755)
        CREDENTIALS.chmod(0o640)
        os.chown(CREDENTIALS, 0, account.pw_gid)
        for path, (data, mode, gid) in changed.items():
            atomic_write(path, data, mode, gid)
        result = subprocess.run(['runuser', '-u', 'telegraf', '--', 'telegraf', '--config', str(CONFIG), '--config-directory', str(CONFIG_DIR), '--test'], capture_output=True, timeout=45)
        log = backup / 'validation.private.log'
        log.write_bytes(result.stdout + result.stderr)
        log.chmod(0o600)
        assert result.returncode == 0 and b'transmission_host_rpc,' in result.stdout and b'transmission,' in result.stdout, 'Native service-user input validation failed; inspect the private backup directory'
        restart_attempted = True
        subprocess.run(['systemctl', 'restart', 'telegraf.service'], check=True, capture_output=True, timeout=30)
        subprocess.run(['systemctl', 'is-active', '--quiet', 'telegraf.service'], check=True)
    except Exception as error:
        if restart_attempted and isinstance(error, subprocess.TimeoutExpired):
            raise RuntimeError('Observe the existing telegraf.service restart job before changing files or requesting another restart; the candidate and backup are retained') from error
        for path, previous in originals.items():
            if previous is None:
                if path.is_file() and path.read_bytes() == changed[path][0]:
                    path.unlink()
            else:
                atomic_write(path, *previous)
        os.chmod(CREDENTIALS, stat.S_IMODE(credential_info.st_mode))
        os.chown(CREDENTIALS, credential_info.st_uid, credential_info.st_gid)
        if restart_attempted:
            subprocess.run(['systemctl', 'restart', 'telegraf.service'], capture_output=True, timeout=30)
        raise
    print(json.dumps({'installed': True, 'backupDirectory': str(backup), 'collectorRestarted': True, 'applicationRestartsRequested': False}))


if __name__ == '__main__':
    main()
