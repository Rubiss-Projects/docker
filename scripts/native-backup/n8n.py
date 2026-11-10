#!/usr/bin/env python3
"""Capture n8n's live SQLite state using confined, descriptor-anchored I/O."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

from confined_files import SafeTree, sqlite_task, identity
import portainer

SOURCE_ROOT = Path('/srv/Docker/n8n/config')
ROOTS = ('.n8n', 'recovery')
REQUIRED_TABLES = {'workflow_entity', 'credentials_entity', 'user', 'execution_entity', 'settings'}
DATABASE_PATH = '.n8n/database.sqlite'


def require_regular_file(path: Path) -> None:
    with SafeTree(path.parent) as tree:
        tree.require_regular(path.name)


def digest(path: Path) -> str:
    with SafeTree(path.parent) as tree:
        return tree.digest(path.name)


def stable_copy(source: Path, destination: Path) -> None:
    with SafeTree(source.parent) as original, SafeTree(destination.parent) as target:
        target.copy_from(original, source.name, destination.name)


def inspect_capture(destination: Path) -> dict:
    """Verify a private restored tree without following captured symlinks."""
    with SafeTree(destination) as job:
        proof = json.loads(job.read('capture.json'))
    with SafeTree(destination/'payload') as payload:
        payload.require_regular('.n8n/config')
        payload.require_regular(DATABASE_PATH)
        if set(proof['sqliteDatabases']) != {DATABASE_PATH}:
            raise ValueError('Capture contains an unadmitted n8n database snapshot')
        if set(payload.walk()) != set(proof['entries']):
            raise ValueError('n8n capture inventory differs from manifest')
        for relative, row in proof['entries'].items():
            value = payload.lstat(relative)
            if row['kind'] == 'file':
                if not stat.S_ISREG(value.st_mode) or value.st_size != row['bytes'] or payload.digest(relative) != row['sha256']:
                    raise ValueError('n8n captured file digest differs')
            elif row['kind'] == 'directory':
                if not stat.S_ISDIR(value.st_mode):
                    raise ValueError('n8n capture directory differs')
            elif row['kind'] == 'symlink':
                if not stat.S_ISLNK(value.st_mode) or payload.readlink(relative) != row['target']:
                    raise ValueError('n8n capture symlink differs')
            else:
                raise ValueError('Unknown n8n capture entry type')
            if payload.metadata(relative) != {key: row[key] for key in ['uid', 'gid', 'mode', 'mtimeNs', 'xattrs']}:
                raise ValueError('n8n capture metadata differs')
        if json.loads(sqlite_task(payload, 'verify', DATABASE_PATH)) != proof['sqliteDatabases'][DATABASE_PATH]:
            raise ValueError('n8n restored database tables differ')
        if not REQUIRED_TABLES.issubset(proof['sqliteDatabases'][DATABASE_PATH]['tableRowCounts']):
            raise ValueError('Required n8n application tables are missing')
        key = json.loads(payload.read('.n8n/config')).get('encryptionKey')
        if not isinstance(key, str) or not key:
            raise ValueError('n8n encryption key is missing')
    return proof


def capture(destination: Path, source_root: Path = SOURCE_ROOT) -> dict:
    if os.geteuid() != 0:
        raise RuntimeError('n8n capture requires the root backup service')
    os.umask(0o077)
    with SafeTree(destination.parent) as parent:
        parent.mkdir(destination.name)
    before = portainer.container_state('n8n')
    if not any(mount['Source'] == str(source_root) and mount['Destination'] == '/root/.n8n'
               for mount in before['Mounts']):
        raise ValueError('Running n8n does not use the admitted source mount')
    environment = dict(value.split('=', 1) for value in before['Config']['Env'])
    if environment.get('DB_TYPE', 'sqlite') != 'sqlite' or environment.get('N8N_ENCRYPTION_KEY'):
        raise ValueError('Expected SQLite and the file-persisted n8n encryption key')
    intent = {'at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'containerId': before['Id'], 'imageId': before['Image'],
              'method': 'sqlite_online_backup_with_paired_key', 'containerControls': 0}
    entries: dict[str, dict] = {}
    databases: dict[str, dict] = {}
    excluded = []
    with SafeTree(destination) as job:
        job.write('intent.json', json.dumps(intent, indent=2).encode())
        job.mkdir('payload')
    with SafeTree(source_root) as source, SafeTree(destination/'payload') as payload:
        for name in ROOTS:
            if not stat.S_ISDIR(source.lstat(name).st_mode):
                raise ValueError('Expected admitted n8n data and recovery directories')
        source.require_regular('.n8n/config')
        source.require_regular(DATABASE_PATH)
        key_before = source.digest('.n8n/config')
        for root in ROOTS:
            for relative in source.walk(root):
                name = PurePosixPath(relative).name
                if (str(PurePosixPath(relative).parent) == '.n8n'
                        and (name == 'crash.journal' or re.fullmatch(r'n8nEventLog(?:-\d+)?\.log', name))
                        and stat.S_ISREG(source.lstat(relative).st_mode)):
                    excluded.append({'path': relative, 'reason': 'live event log or crash journal'})
                    continue
                if relative in {DATABASE_PATH+suffix for suffix in ['-wal', '-shm', '-journal']}:
                    excluded.append({'path': relative, 'reason': 'SQLite sidecar included through online backup'})
                    continue
                row = source.metadata(relative)
                original = source.lstat(relative)
                if stat.S_ISDIR(original.st_mode):
                    payload.mkdir(relative)
                    row['kind'] = 'directory'
                elif stat.S_ISLNK(original.st_mode):
                    target = source.readlink(relative)
                    payload.symlink(relative, target)
                    row.update(kind='symlink', target=target)
                elif stat.S_ISREG(original.st_mode):
                    if relative == DATABASE_PATH:
                        # The child sees only the pinned source directory. SQLite
                        # can open its live WAL without access to the host root.
                        payload.write(relative, sqlite_task(source, 'snapshot', DATABASE_PATH))
                        if identity(source.lstat(relative)) != identity(original):
                            raise ValueError('n8n database was replaced during capture')
                        databases[relative] = json.loads(sqlite_task(payload, 'normalize', DATABASE_PATH))
                        row['captureMethod'] = 'sqlite_online_backup'
                    else:
                        row = payload.copy_from(source, relative)
                        row['captureMethod'] = 'stable_file_copy'
                    row.update(kind='file', bytes=payload.lstat(relative).st_size, sha256=payload.digest(relative))
                else:
                    raise ValueError('Unexpected special file in n8n persistent state')
                entries[relative] = row
        if source.digest('.n8n/config') != key_before or payload.digest('.n8n/config') != key_before:
            raise ValueError('n8n key changed while snapshotting its database')
        after = portainer.container_state('n8n')
        if portainer.identity(before) != portainer.identity(after):
            raise ValueError('n8n container changed during capture')
        for relative, row in sorted(entries.items(), key=lambda item: len(PurePosixPath(item[0]).parts), reverse=True):
            payload.apply_metadata(relative, row)
    proof = {**intent, 'entries': entries, 'sqliteDatabases': databases,
             'excludedTransientEntries': excluded, 'pairedEncryptionKeyUnchanged': True,
             'containerIdentityUnchanged': True, 'independentRestorePending': True,
             'databaseAndSupportingFilesNotCrossFileAtomic': True,
             'encryptedRepositoryCapturePending': True}
    with SafeTree(destination) as job:
        job.write('capture.json', json.dumps(proof, indent=2).encode())
    inspect_capture(destination)
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['capture', 'verify'])
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    result = capture(args.destination) if args.operation == 'capture' else inspect_capture(args.destination)
    print(json.dumps({'method': result['method'], 'entries': len(result['entries']),
                      'sqliteDatabases': len(result['sqliteDatabases']), 'containerControls': 0,
                      'pairedEncryptionKeyUnchanged': result['pairedEncryptionKeyUnchanged']}))


if __name__ == '__main__':
    main()

