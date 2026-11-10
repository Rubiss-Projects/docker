#!/usr/bin/env python3
"""Capture Portainer's supported online backup without stopping its container."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import urllib.request


MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024 * 1024
BBOLT_SHA256 = 'f2b8a5b096621ce2dd32801455de9b07d3742a3010149f25040ae0d6ff1784e1'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Backup endpoint redirects are not permitted')


def inspect_archive(archive: Path, bbolt: Path) -> dict:
    """Read every regular member; send only the database to a private verifier."""
    names: set[str] = set()
    files: dict[str, dict] = {}
    total = 0
    database_seen = False
    with tempfile.TemporaryDirectory(prefix='portainer-verify-', dir=archive.parent) as directory:
        database = Path(directory) / 'portainer.db'
        # Vendor archives use /portainer.db. Never extract absolute archive paths.
        with tarfile.open(archive, 'r|gz') as stream:
            for member in stream:
                path = PurePosixPath(member.name)
                if '..' in path.parts or '\\' in member.name:
                    raise ValueError('Unsafe backup member path')
                name = str(path).lstrip('/')
                if not name or name in names:
                    raise ValueError('Empty or duplicate backup member')
                names.add(name)
                if len(names) > 10000:
                    raise ValueError('Too many backup members')
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError('Unsupported backup member type')
                total += member.size
                if total > MAX_PAYLOAD_BYTES:
                    raise ValueError('Backup payload exceeds configured safety limit')
                digest = hashlib.sha256()
                count = 0
                source = stream.extractfile(member)
                if source is None:
                    raise ValueError('Unreadable backup member')
                target = database.open('xb') if name == 'portainer.db' else None
                try:
                    while chunk := source.read(1024 * 1024):
                        count += len(chunk)
                        digest.update(chunk)
                        if target is not None:
                            target.write(chunk)
                finally:
                    source.close()
                    if target is not None:
                        target.close()
                if count != member.size:
                    raise ValueError('Truncated backup member')
                files[name] = {'bytes': count, 'sha256': digest.hexdigest()}
                database_seen |= name == 'portainer.db'
        if not database_seen:
            raise ValueError('Backup has no root Portainer database')
        result = subprocess.run([str(bbolt), 'check', str(database)],
                                capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0 or result.stdout.strip() != 'OK' or result.stderr.strip():
            raise ValueError('Portainer backup database failed bbolt consistency check')
    # The tar parser can stop before the gzip trailer. Read the complete compressed
    # stream separately so truncated archives or a bad gzip CRC cannot pass.
    import gzip
    with gzip.open(archive, 'rb') as source:
        count = 0
        while chunk := source.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_PAYLOAD_BYTES + 16 * 1024 * 1024:
                raise ValueError('Expanded archive exceeds safety limit')
    return {'files': files, 'regularFiles': len(files), 'regularBytes': total,
            'databaseBboltCheck': 'OK', 'fullGzipReadback': True}


def container_state(container: str) -> dict:
    rows = json.loads(subprocess.check_output(['docker', 'inspect', container]))
    if len(rows) != 1 or not rows[0]['State']['Running']:
        raise ValueError('Expected one running Portainer container')
    return rows[0]


def identity(state: dict) -> tuple:
    return state['Id'], state['State']['StartedAt'], state['RestartCount'], state['Image']


def capture(destination: Path, bbolt: Path, container: str = 'portainer') -> dict:
    os.umask(0o077)
    # A retained directory means a request may already have been sent. Reconcile it;
    # never repeat POST merely because a client or an observer timed out.
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    before = container_state(container)
    token = before['Config']['Labels']['homepage.widget.key']
    address = next(value['IPAddress'] for value in before['NetworkSettings']['Networks'].values()
                   if value.get('IPAddress'))
    if not ipaddress.ip_address(address).is_private:
        raise ValueError('Backup transport must use the local Docker network')
    intent = {'containerId': before['Id'], 'imageId': before['Image'],
              'method': 'supported_online_backup_api', 'containerControls': 0}
    (destination/'intent.json').write_text(json.dumps(intent, indent=2))
    request = urllib.request.Request(f'http://{address}:9000/api/backup',
        data=b'{"Password":""}', method='POST',
        headers={'Content-Type': 'application/json', 'X-API-Key': token})
    partial = destination/'backup.tar.gz.partial'
    # Ignore controller proxy settings for this direct, authenticated local request.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=120) as response, partial.open('xb') as output:
        if response.status != 200:
            raise ValueError('Portainer backup API did not succeed')
        count = 0
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_ARCHIVE_BYTES:
                raise ValueError('Compressed backup exceeds safety limit')
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    del request, token
    proof = inspect_archive(partial, bbolt)
    after = container_state(container)
    if identity(before) != identity(after):
        raise ValueError('Portainer identity changed during capture; reconcile retained archive')
    archive = destination/'backup.tar.gz'
    partial.rename(archive)
    with archive.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    proof.update(intent, archiveBytes=archive.stat().st_size, archiveSha256=digest,
                 containerIdentityUnchanged=True, encryptedRepositoryCapturePending=True)
    (destination/'capture.json').write_text(json.dumps(proof, indent=2))
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['capture', 'verify'])
    parser.add_argument('path', type=Path)
    parser.add_argument('--bbolt', required=True, type=Path)
    parser.add_argument('--container', default='portainer')
    args = parser.parse_args()
    with args.bbolt.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != BBOLT_SHA256:
            parser.error('bbolt binary does not match the admitted Linux amd64 verifier')
    if args.operation == 'capture':
        result = capture(args.path, args.bbolt, args.container)
    else:
        result = inspect_archive(args.path, args.bbolt)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
