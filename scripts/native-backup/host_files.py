"""Confined host-tree capture with online SQLite snapshots and link preservation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from confined_files import SafeTree, identity, sqlite_snapshot_file, sqlite_task

METADATA = ('uid', 'gid', 'mode', 'mtimeNs', 'xattrs')


def sqlite_header(tree: SafeTree, relative: str) -> bool:
    with tree.fd(relative, os.O_RDONLY | os.O_NONBLOCK) as descriptor:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('Expected a regular source file')
        return os.read(descriptor, 16) == b'SQLite format 3\x00'


def capture_tree(source_root: Path, destination: Path, selected: str = '.') -> dict:
    """Capture a selected subtree; every SQLite reader is chrooted to its root.

    The caller admits each source root and creates the private destination.
    Individual databases are consistent, but the whole host is not atomic.
    """
    if source_root.absolute() == Path('/'):
        raise ValueError('Host root is not an admitted SQLite confinement boundary')
    entries = {}
    databases = {}
    excluded = []
    with SafeTree(source_root) as source, SafeTree(destination) as target:
        paths = list(source.walk(selected))
        sqlite_paths = {p for p in paths if stat.S_ISREG(source.lstat(p).st_mode)
                        and sqlite_header(source, p)}
        sidecars = {name+suffix for name in sqlite_paths for suffix in ['-wal', '-shm', '-journal']}
        for relative in paths:
            value = source.lstat(relative)
            if relative in sidecars:
                if not stat.S_ISREG(value.st_mode):
                    raise ValueError('Unexpected non-regular SQLite sidecar')
                excluded.append({'path': relative, 'reason': 'SQLite sidecar included through online backup'})
                continue
            if not (stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or stat.S_ISREG(value.st_mode)):
                # Scope admission currently contains no such entries. A new
                # socket/device needs an explicit non-restorative disposition.
                raise ValueError('Unadmitted special file in host persistent state')
            row = source.metadata(relative)
            if stat.S_ISDIR(value.st_mode):
                target.mkdir(relative)
                row['kind'] = 'directory'
            elif stat.S_ISLNK(value.st_mode):
                link = source.readlink(relative)
                target.symlink(relative, link)
                row.update(kind='symlink', target=link)
            else:
                if relative in sqlite_paths:
                    sqlite_snapshot_file(source, relative, target, relative)
                    if identity(value) != identity(source.lstat(relative)):
                        raise ValueError('Host database was replaced during capture')
                    databases[relative] = json.loads(sqlite_task(target, 'normalize', relative))
                    row['captureMethod'] = 'sqlite_online_backup'
                else:
                    row = target.copy_from(source, relative)
                    row['captureMethod'] = 'stable_file_copy'
                row.update(kind='file', bytes=target.lstat(relative).st_size,
                           sha256=target.digest(relative))
            entries[relative] = row
        for relative, row in sorted(entries.items(), key=lambda item: item[0].count('/'), reverse=True):
            target.apply_metadata(relative, row)
        root_metadata = source.metadata('.') if selected == '.' else None
        if root_metadata is not None:
            target.apply_metadata('.', root_metadata)
    proof = {'entries': entries, 'sqliteDatabases': databases,
             'excludedTransientEntries': excluded, 'rootMetadata': root_metadata,
             'individualDatabaseSnapshotsNotCrossDatabaseAtomic': True}
    inspect_tree(destination, proof)
    return proof


def inspect_tree(destination: Path, proof: dict) -> None:
    with SafeTree(destination) as tree:
        if set(tree.walk()) != set(proof['entries']):
            raise ValueError('Host restored tree inventory differs')
        for relative, row in proof['entries'].items():
            value = tree.lstat(relative)
            if row['kind'] == 'file':
                if not stat.S_ISREG(value.st_mode) or value.st_size != row['bytes'] or tree.digest(relative) != row['sha256']:
                    raise ValueError('Host restored file differs')
            elif row['kind'] == 'directory':
                if not stat.S_ISDIR(value.st_mode):
                    raise ValueError('Host restored directory differs')
            elif row['kind'] == 'symlink':
                if not stat.S_ISLNK(value.st_mode) or tree.readlink(relative) != row['target']:
                    raise ValueError('Host restored symlink differs')
            else:
                raise ValueError('Unknown host recovery entry kind')
            if tree.metadata(relative) != {k: row[k] for k in METADATA}:
                raise ValueError('Host restored metadata differs')
        if proof['rootMetadata'] is not None and tree.metadata('.') != proof['rootMetadata']:
            raise ValueError('Host restored root metadata differs')
        for relative, expected in proof['sqliteDatabases'].items():
            if json.loads(sqlite_task(tree, 'verify', relative)) != expected:
                raise ValueError('Host restored SQLite table counts differ')
