#!/usr/bin/env python3
"""Install native Caddy and reload its private SWAG hop; no container restarts."""

import argparse
import datetime
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import runpy
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

SOURCE = Path(__file__).resolve().parent


def channels_config():
    # One encrypted source supplies both ends. Strict hex also prevents injecting
    # directives into either configuration. Never print the generated material.
    value = (SOURCE / 'channels-lan.env.secret').read_text().strip()
    match = re.fullmatch(r'CHANNELS_LAN_KEY=([0-9a-f]{64})', value)
    if not match:
        raise ValueError('Missing/unusable decrypted Channels relay key')
    key = match[1]
    native = (SOURCE / 'channels-lan.caddy').read_text().replace('@CHANNELS_LAN_KEY@', key)
    # Case-sensitive, anchored regex rather than nginx map's case-folded strings.
    return native.encode(), f'~^{key}$ 1;\n'.encode()


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60)


def install_file(destination, data, mode, group):
    # Unique candidates let a new invocation recover after an interrupted write.
    descriptor, name = tempfile.mkstemp(prefix=destination.name + '.', suffix='.new', dir=destination.parent)
    candidate = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
            os.fchown(out.fileno(), 0, group)
            os.fchmod(out.fileno(), mode)
        candidate.replace(destination)
    finally:
        candidate.unlink(missing_ok=True)


def publish(items, backup):
    # Hold the same lock as certificate refresh and watchdog remediation until
    # every file is installed, validated and known to systemd. Call sync in this
    # process to avoid the certificate CLI trying to acquire our lock again.
    with open('/run/lock/caddy-plex.lock', 'a') as operation:
        fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        installed_binary = Path('/usr/local/bin/caddy-plex')
        active = subprocess.run(['systemctl', 'is-active', '--quiet', 'caddy-plex.service']).returncode == 0
        if active and installed_binary.read_bytes() != items[installed_binary][0]:
            raise RuntimeError('Binary upgrade requires a noticed Caddy-only stop; no files changed')
        originals = {}
        for destination in items:
            originals[str(destination)] = destination.exists()
            if destination.exists():
                shutil.copy2(destination, backup / destination.name)
        (backup / 'files.json').write_text(json.dumps(originals, indent=2))
        for destination, (data, mode, group) in items.items():
            install_file(destination, data, mode, group)
        certificate = runpy.run_path('/usr/local/lib/caddy-plex/certificate.py')
        certificate['sync'](reload_active=False)
        run('/usr/local/bin/caddy-plex', 'validate', '--config', '/etc/caddy-plex/Caddyfile', '--adapter', 'caddyfile')
        run('docker', 'exec', 'swag', 'nginx', '-t')
        run('docker', 'exec', 'swag', 'nginx', '-s', 'reload')
        run('systemctl', 'daemon-reload')
        if subprocess.run(['systemctl', 'is-active', '--quiet', 'caddy-plex.service']).returncode == 0:
            run('/usr/local/bin/caddy-plex', 'reload', '--force', '--config', '/etc/caddy-plex/Caddyfile',
                '--adapter', 'caddyfile', '--address', 'unix//run/caddy-plex/admin.sock')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Optional predownloaded official release archive')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root in Ubuntu')
    if Path('/run/caddy-plex.maintenance').exists():
        raise SystemExit('Caddy maintenance hold present')
    if SOURCE != Path('/mnt/e/Docker/caddy'):
        raise SystemExit('Install the merged source from /mnt/e/Docker/caddy')
    os.umask(0o077)
    # chmod/chown silently leave 1000:1000/777 on this host's VirtioFS mount.
    # The fixed Windows helper protects just these key paths before publication.
    run('/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile',
        '-ExecutionPolicy', 'Bypass', '-File', 'E:\\Docker\\caddy\\protect-channels-key.ps1')
    channels_native, channels_guard = channels_config()
    release = json.loads((SOURCE / 'release.json').read_text())
    with tempfile.TemporaryDirectory(prefix='caddy-install-') as temp:
        archive = args.archive or Path(temp) / 'caddy.tar.gz'
        if args.archive is None:
            with urllib.request.urlopen(release['url'], timeout=60) as response, archive.open('wb') as out:
                shutil.copyfileobj(response, out)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != release['sha256']:
            raise SystemExit('Caddy archive checksum mismatch')
        with tarfile.open(archive) as bundle:
            member = bundle.getmember('caddy')
            if not member.isfile():
                raise SystemExit('Caddy archive member is not a regular file')
            binary = bundle.extractfile(member).read()
        try:
            pwd.getpwnam('caddy-plex')
        except KeyError:
            run('useradd', '--system', '--user-group', '--home-dir', '/var/lib/caddy-plex',
                '--shell', '/usr/sbin/nologin', 'caddy-plex')
        gid = grp.getgrnam('caddy-plex').gr_gid
        for directory, mode, group in [('/etc/caddy-plex', 0o750, gid),
                                       ('/etc/caddy-plex/tls', 0o750, gid),
                                       ('/usr/local/lib/caddy-plex', 0o755, 0),
                                       ('/var/lib/caddy-plex-control', 0o700, 0)]:
            path = Path(directory)
            path.mkdir(exist_ok=True, parents=True)
            os.chown(path, 0, group)
            path.chmod(mode)
        items = {Path('/usr/local/bin/caddy-plex'): (binary, 0o755, 0)}
        items[Path('/etc/caddy-plex/Caddyfile')] = ((SOURCE / 'Caddyfile').read_bytes(), 0o640, gid)
        items[Path('/etc/caddy-plex/channels-lan.caddy')] = (channels_native, 0o640, gid)
        guard_dir = SOURCE.parent / 'swag/config/nginx/channels-lan-private'
        guard_dir.mkdir(mode=0o700, exist_ok=True)
        if any(path.name != 'key.conf' for path in guard_dir.glob('*.conf')):
            raise RuntimeError('Unexpected Channels key include; refusing ambiguous authorization')
        items[guard_dir / 'key.conf'] = (channels_guard, 0o600, 0)
        for name in ('certificate.py', 'health.py'):
            items[Path('/usr/local/lib/caddy-plex') / name] = ((SOURCE / name).read_bytes(), 0o644, 0)
        for path in SOURCE.glob('*.service'):
            items[Path('/etc/systemd/system') / path.name] = (path.read_bytes(), 0o644, 0)
        items[Path('/etc/systemd/system/caddy-plex-certificate.timer')] = (
            (SOURCE / 'caddy-plex-certificate.timer').read_bytes(), 0o644, 0)
        backup = Path('/var/lib/caddy-plex-control') / datetime.datetime.now(datetime.timezone.utc).strftime('install-%Y%m%dT%H%M%S%fZ')
        backup.mkdir(mode=0o700)
        try:
            publish(items, backup)
            # Startup may activate the certificate dependency, so release the
            # operational lock only after publication/validation/daemon-reload.
            run('systemctl', 'enable', 'caddy-plex.service', 'caddy-plex-certificate.timer')
            run('systemctl', 'start', 'caddy-plex-certificate.timer')
            run('systemctl', 'start', 'caddy-plex.service')
            run('python3', '/usr/local/lib/caddy-plex/health.py')
        except Exception:
            # Keep originals for a concrete rollback. Never restart Docker or
            # silently change routing if this installation has a problem.
            print('Installation failed; originals retained at ' + str(backup))
            raise
        print('Caddy installed and HTTPS health passed. Originals: ' + str(backup))


if __name__ == '__main__':
    with open('/run/lock/caddy-plex-install.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
