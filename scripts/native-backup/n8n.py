#!/usr/bin/env python3
"""Capture n8n's SQLite state and paired key without controlling its container."""

from __future__ import annotations

import argparse
import base64
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time

import portainer

SOURCE_ROOT = Path('/srv/Docker/n8n/config')
ROOTS = ('.n8n', 'recovery')
REQUIRED_TABLES = {'workflow_entity', 'credentials_entity', 'user', 'execution_entity', 'settings'}
DATABASE_PATH = '.n8n/database.sqlite'


def require_regular_file(path: Path) -> None:
    if not stat.S_ISREG(path.lstat().st_mode) or path.resolve() != path.absolute():
        raise ValueError('n8n key and database must be regular files within the captured root')


def digest(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def metadata(path: Path) -> dict:
    value = path.lstat()
    return {'uid': value.st_uid, 'gid': value.st_gid, 'mode': stat.S_IMODE(value.st_mode),
            'mtimeNs': value.st_mtime_ns,
            'xattrs': {key: base64.b64encode(os.getxattr(path, key, follow_symlinks=False)).decode()
                       for key in os.listxattr(path, follow_symlinks=False)}}


def apply_metadata(path: Path, row: dict) -> None:
    symlink = path.is_symlink()
    os.chown(path, row['uid'], row['gid'], follow_symlinks=not symlink)
    if not symlink:
        path.chmod(row['mode'])
    os.utime(path, ns=(row['mtimeNs'], row['mtimeNs']), follow_symlinks=not symlink)
    for key, value in row['xattrs'].items():
        os.setxattr(path, key, base64.b64decode(value), follow_symlinks=not symlink)


def sqlite_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with path.open('rb') as source:
        return source.read(16) == b'SQLite format 3\0'


def database_proof(path: Path) -> dict:
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=30)) as database:
        if database.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('n8n database integrity check failed')
        tables = [row[0] for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {name: database.execute('SELECT count(*) FROM "'+name.replace('"', '""')+'"').fetchone()[0]
                  for name in tables}
    return {'integrityCheck': 'ok', 'tableRowCounts': counts}


def snapshot_database(source: Path, destination: Path) -> dict:
    deadline = time.monotonic()+120

    def progress(status: int, remaining: int, total: int) -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError('Online n8n database snapshot exceeded its deadline')

    with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=30)) as original:
        with closing(sqlite3.connect(destination)) as target:
            original.backup(target, pages=1024, progress=progress, sleep=.05)
            # A standalone snapshot must not need WAL/shm files when reopened.
            if target.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                raise ValueError('Could not finalize a standalone SQLite snapshot')
    return database_proof(destination)


def stable_copy(source: Path, destination: Path) -> None:
    # File mutation is a failed capture, never permission to publish mixed bytes.
    before = source.stat()
    with source.open('rb') as input_file, destination.open('xb') as output:
        while block := input_file.read(1024*1024):
            output.write(block)
        output.flush()
        os.fsync(output.fileno())
    after = source.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('n8n supporting file changed during capture')


def inspect_capture(destination: Path) -> dict:
    """Verify the restored tree and SQLite snapshot without loading n8n or secrets."""
    proof = json.loads((destination/'capture.json').read_text())
    payload = destination/'payload'
    require_regular_file(payload/'.n8n/config')
    require_regular_file(payload/DATABASE_PATH)
    if set(proof['sqliteDatabases']) != {DATABASE_PATH}:
        raise ValueError('Capture contains an unadmitted n8n database snapshot')
    actual = set()
    for directory, directories, files in os.walk(payload, followlinks=False):
        for name in directories+files:
            actual.add((Path(directory)/name).relative_to(payload).as_posix())
    if actual != set(proof['entries']):
        raise ValueError('n8n capture inventory differs from manifest')
    for relative, row in proof['entries'].items():
        path = payload/relative
        if path.is_absolute() and not path.is_relative_to(payload):
            raise ValueError('n8n manifest path leaves payload')
        if '..' in Path(relative).parts or Path(relative).is_absolute():
            raise ValueError('Unsafe n8n capture path')
        value = path.lstat()
        if row['kind'] == 'file':
            if not stat.S_ISREG(value.st_mode) or value.st_size != row['bytes'] or digest(path) != row['sha256']:
                raise ValueError('n8n captured file digest differs')
        elif row['kind'] == 'directory':
            if not stat.S_ISDIR(value.st_mode):
                raise ValueError('n8n capture directory differs')
        elif row['kind'] == 'symlink':
            if not stat.S_ISLNK(value.st_mode) or os.readlink(path) != row['target']:
                raise ValueError('n8n capture symlink differs')
        else:
            raise ValueError('Unknown n8n capture entry type')
        if metadata(path) != {key: row[key] for key in ['uid', 'gid', 'mode', 'mtimeNs', 'xattrs']}:
            raise ValueError('n8n capture metadata differs')
    for relative, expected in proof['sqliteDatabases'].items():
        if database_proof(payload/relative) != expected:
            raise ValueError('n8n restored database tables differ')
    database = proof['sqliteDatabases']['.n8n/database.sqlite']
    if not REQUIRED_TABLES.issubset(database['tableRowCounts']):
        raise ValueError('Required n8n application tables are missing')
    key = json.loads((payload/'.n8n/config').read_text()).get('encryptionKey')
    if not isinstance(key, str) or not key:
        raise ValueError('n8n encryption key is missing')
    return proof


def capture(destination: Path, source_root: Path = SOURCE_ROOT) -> dict:
    os.umask(0o077)
    destination.mkdir(mode=0o700, exist_ok=False)
    if source_root.resolve() != source_root or not all(
            (source_root/name).is_dir() and (source_root/name).resolve() == source_root/name for name in ROOTS):
        raise ValueError('Expected admitted n8n data and recovery roots')
    before = portainer.container_state('n8n')
    if not any(mount['Source'] == str(source_root) and mount['Destination'] == '/root/.n8n'
               for mount in before['Mounts']):
        raise ValueError('Running n8n does not use the admitted source mount')
    environment = dict(value.split('=', 1) for value in before['Config']['Env'])
    if environment.get('DB_TYPE', 'sqlite') != 'sqlite' or environment.get('N8N_ENCRYPTION_KEY'):
        raise ValueError('Expected SQLite and the file-persisted n8n encryption key')
    key_file = source_root/'.n8n/config'
    require_regular_file(key_file)
    require_regular_file(source_root/DATABASE_PATH)
    key_before = digest(key_file)
    intent = {'at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'containerId': before['Id'], 'imageId': before['Image'],
              'method': 'sqlite_online_backup_with_paired_key', 'containerControls': 0}
    (destination/'intent.json').write_text(json.dumps(intent, indent=2))
    payload = destination/'payload'
    payload.mkdir(mode=0o700)
    entries: dict[str, dict] = {}
    databases: dict[str, dict] = {}
    excluded = []

    def copy(path: Path) -> None:
        relative = path.relative_to(source_root).as_posix()
        if path.name.startswith('n8nEventLog') or path.name == 'crash.journal':
            excluded.append({'path': relative, 'reason': 'live event log or crash journal'})
            return
        if relative in {DATABASE_PATH+suffix for suffix in ['-wal', '-shm', '-journal']}:
            excluded.append({'path': relative, 'reason': 'SQLite sidecar included through online backup'})
            return
        row = metadata(path)
        mode = path.lstat().st_mode
        target = payload/relative
        if stat.S_ISDIR(mode):
            target.mkdir(mode=0o700)
            row['kind'] = 'directory'
        elif stat.S_ISLNK(mode):
            target.symlink_to(os.readlink(path))
            row.update(kind='symlink', target=os.readlink(path))
        elif stat.S_ISREG(mode):
            if relative == DATABASE_PATH:
                if not sqlite_file(path):
                    raise ValueError('Admitted n8n database has no SQLite header')
                databases[relative] = snapshot_database(path, target)
                row['captureMethod'] = 'sqlite_online_backup'
            else:
                stable_copy(path, target)
                row['captureMethod'] = 'stable_file_copy'
            row.update(kind='file', bytes=target.stat().st_size, sha256=digest(target))
        else:
            raise ValueError('Unexpected special file in n8n persistent state')
        entries[relative] = row

    for root in ROOTS:
        copy(source_root/root)
        for directory, directories, files in os.walk(source_root/root, followlinks=False):
            for name in sorted(directories+files):
                copy(Path(directory)/name)
    if digest(key_file) != key_before or digest(payload/'.n8n/config') != key_before:
        raise ValueError('n8n key changed while snapshotting its database')
    after = portainer.container_state('n8n')
    if portainer.identity(before) != portainer.identity(after):
        raise ValueError('n8n container changed during capture')
    for relative, row in sorted(entries.items(), key=lambda item: len(Path(item[0]).parts), reverse=True):
        apply_metadata(payload/relative, row)
    proof = {**intent, 'entries': entries, 'sqliteDatabases': databases,
             'excludedTransientEntries': excluded, 'pairedEncryptionKeyUnchanged': True,
             'containerIdentityUnchanged': True, 'independentRestorePending': True,
             'databaseAndSupportingFilesNotCrossFileAtomic': True,
             'encryptedRepositoryCapturePending': True}
    (destination/'capture.json').write_text(json.dumps(proof, indent=2))
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

