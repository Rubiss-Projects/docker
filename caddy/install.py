#!/usr/bin/env python3
"""Install the reviewed native Ubuntu proxy; no Plex/router/Docker changes."""

import argparse
import datetime
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

SOURCE = Path(__file__).resolve().parent


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Optional predownloaded official release archive')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root in Ubuntu')
    if Path('/run/caddy-plex.maintenance').exists():
        raise SystemExit('Caddy maintenance hold present')
    os.umask(0o077)
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
        active = subprocess.run(['systemctl', 'is-active', '--quiet', 'caddy-plex.service']).returncode == 0
        installed_binary = Path('/usr/local/bin/caddy-plex')
        if active and installed_binary.read_bytes() != binary:
            raise SystemExit('Binary upgrade requires a noticed Caddy-only stop; no files changed')
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
        for name in ('certificate.py', 'health.py'):
            items[Path('/usr/local/lib/caddy-plex') / name] = ((SOURCE / name).read_bytes(), 0o644, 0)
        for path in SOURCE.glob('*.service'):
            items[Path('/etc/systemd/system') / path.name] = (path.read_bytes(), 0o644, 0)
        items[Path('/etc/systemd/system/caddy-plex-certificate.timer')] = (
            (SOURCE / 'caddy-plex-certificate.timer').read_bytes(), 0o644, 0)
        backup = Path('/var/lib/caddy-plex-control') / datetime.datetime.now(datetime.timezone.utc).strftime('install-%Y%m%dT%H%M%S%fZ')
        backup.mkdir(mode=0o700)
        originals = {}
        for destination, (data, mode, group) in items.items():
            originals[str(destination)] = destination.exists()
            if destination.exists():
                shutil.copy2(destination, backup / destination.name)
            candidate = destination.with_name(destination.name + '.new')
            with candidate.open('xb') as out:
                out.write(data)
            os.chown(candidate, 0, group)
            candidate.chmod(mode)
            candidate.replace(destination)
        (backup / 'files.json').write_text(json.dumps(originals, indent=2))
        # Boot certificate creation is handled by the dependency; perform the
        # initial copy here too so validation can happen before starting Caddy.
        try:
            run('python3', '/usr/local/lib/caddy-plex/certificate.py')
            run('/usr/local/bin/caddy-plex', 'validate', '--config', '/etc/caddy-plex/Caddyfile', '--adapter', 'caddyfile')
            run('systemctl', 'daemon-reload')
            run('systemctl', 'enable', 'caddy-plex.service', 'caddy-plex-certificate.timer')
            run('systemctl', 'start', 'caddy-plex-certificate.timer')
            run('systemctl', 'reload' if active else 'start', 'caddy-plex.service')
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
