#!/usr/bin/env python3
"""Restore native permissions only on Git-tracked source and its parent folders."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import NamedTuple


class Change(NamedTuple):
    path: Path
    mode: int
    inode: int
    directory: bool


def plan(repo: Path) -> list[Change]:
    if not repo.is_absolute() or repo.resolve() != repo or repo.stat().st_uid != os.geteuid():
        raise ValueError('Checkout must be a real directory owned by the caller')
    entries = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '--stage', '-z']).split(b'\0')
    tracked = []
    for entry in filter(None, entries):
        header, name = entry.split(b'\t', 1)
        mode, _, stage = header.split()
        relative = Path(os.fsdecode(name))
        if stage != b'0' or mode not in {b'100644', b'100755', b'120000'} or relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsupported index entry; no permissions changed')
        tracked.append((relative, mode))
    names = b'\0'.join(os.fsencode(path) for path, _ in tracked) + b'\0'
    attributes = subprocess.check_output(['git', '-C', str(repo), 'check-attr', '-z', '--stdin', 'filter'], input=names).split(b'\0')
    if attributes[-1:] != [b''] or (len(attributes)-1) % 3:
        raise ValueError('Invalid Git attribute response')
    encrypted = {Path(os.fsdecode(attributes[i])) for i in range(0, len(attributes)-1, 3)
                 if attributes[i+1] == b'filter' and (attributes[i+2] == b'git-crypt' or attributes[i+2].startswith(b'git-crypt-'))}
    directories = {repo}
    files = []
    for relative, index_mode in tracked:
        path = repo / relative
        for parent in path.parents:
            if parent == repo.parent:
                break
            directories.add(parent)
        info = path.lstat()
        if index_mode == b'120000':
            if not stat.S_ISLNK(info.st_mode) or relative in encrypted:
                raise ValueError('Unexpected or encrypted symlink')
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError('Tracked source must be a regular file owned by the caller')
        files.append(Change(path, 0o600 if relative in encrypted else 0o755 if index_mode == b'100755' else 0o644, info.st_ino, False))
    parents = []
    for path in sorted(directories, key=lambda p: (len(p.parts), str(p))):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError('Tracked parent must be an owned real directory')
        parents.append(Change(path, 0o755, info.st_ino, True))
    return parents + files


def apply(changes: list[Change]) -> None:
    for path, mode, inode, directory in changes:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
            if info.st_ino != inode or info.st_uid != os.geteuid() or not correct_type:
                raise ValueError('Source identity changed during permission repair')
            if stat.S_IMODE(info.st_mode) != mode:
                os.fchmod(descriptor, mode)
        finally:
            os.close(descriptor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('/srv/Docker'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    changes = plan(args.repo)
    needed = sum(stat.S_IMODE(c.path.lstat().st_mode) != c.mode for c in changes)
    if args.apply:
        apply(changes)
    print(json.dumps({'trackedPathsAndParentsChecked': len(changes), 'permissionChangesNeeded': needed,
                      'applied': args.apply, 'untrackedFilesChanged': 0, 'ownershipChanged': False}))


if __name__ == '__main__':
    main()
