#!/usr/bin/env python3
"""Validate and atomically publish a private TLS pair; reload only on change."""

import fcntl
import grp
import hashlib
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile

SOURCE = Path('/mnt/e/Docker/swag/config/keys/letsencrypt')
DESTINATION = Path('/etc/caddy-plex/tls')
HOST = 'plex-remote.benlawson.dev'
FILES = ('fullchain.pem', 'privkey.pem')


def validate(directory):
    # OpenSSL verifies dates, hostname and key match without emitting key bytes.
    subprocess.run(['openssl', 'x509', '-in', str(directory / FILES[0]),
                    '-noout', '-checkend', '86400'],
                   check=True, capture_output=True, timeout=5)
    result = subprocess.run(['openssl', 'x509', '-in', str(directory / FILES[0]),
                    '-noout', '-checkhost', HOST],
                   check=True, capture_output=True, text=True, timeout=5)
    if f'Hostname {HOST} does match certificate' not in result.stdout:
        raise ValueError('Certificate does not cover the Plex proxy hostname')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(directory / FILES[0], directory / FILES[1])


def sync(source=SOURCE, destination=DESTINATION):
    content = {name: (source / name).read_bytes() for name in FILES}
    fingerprint = hashlib.sha256(b''.join(content.values())).hexdigest()
    current = destination / 'current'
    # A failed previous reload must be retried even when the copy is unchanged.
    loaded = destination / 'loaded.sha256'
    gid = grp.getgrnam('caddy-plex').gr_gid
    candidate = Path(tempfile.mkdtemp(prefix='.candidate-', dir=destination))
    previous = os.readlink(current) if current.is_symlink() else None
    changed = False
    try:
        os.chown(candidate, 0, gid)
        candidate.chmod(0o750)
        for name, data in content.items():
            path = candidate / name
            path.write_bytes(data)
            os.chown(path, 0, gid)
            path.chmod(0o640)
        validate(candidate)
        if any((source / name).read_bytes() != data for name, data in content.items()):
            raise RuntimeError('Certificate changed during copy; waiting for next timer')
        version = destination / fingerprint
        if not version.exists():
            candidate.rename(version)
        else:
            if any((version / name).read_bytes() != data for name, data in content.items()):
                raise RuntimeError('Certificate version content mismatch')
        if previous != fingerprint:
            link = destination / '.next'
            link.symlink_to(fingerprint)
            link.replace(current)
            changed = True
        active = subprocess.run(['systemctl', 'is-active', '--quiet', 'caddy-plex.service']).returncode == 0
        if active and (changed or not loaded.exists() or loaded.read_text() != fingerprint):
            subprocess.run(['/usr/local/bin/caddy-plex', 'reload', '--force', '--config',
                            '/etc/caddy-plex/Caddyfile', '--adapter', 'caddyfile',
                            '--address', 'unix//run/caddy-plex/admin.sock'],
                           check=True, capture_output=True, timeout=20)
            loaded.write_text(fingerprint)
        print('Caddy certificate ready' + ('; reloaded' if active and changed else ''))
    except Exception:
        if changed and previous is not None:
            link = destination / '.backout'
            link.symlink_to(previous)
            link.replace(current)
        raise
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)


if __name__ == '__main__':
    os.umask(0o077)
    with open('/run/lock/caddy-plex.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sync()
