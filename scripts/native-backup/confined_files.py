"""Linux descriptor-anchored capture I/O and confined SQLite operations."""

from __future__ import annotations

import base64
from contextlib import contextmanager, closing
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import subprocess
import sys
import time


class OpenHow(ctypes.Structure):
    _fields_ = [('flags', ctypes.c_uint64), ('mode', ctypes.c_uint64),
                ('resolve', ctypes.c_uint64)]


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value:
        raise ValueError('Unsafe capture-relative path')
    return value


def open_beneath(directory: int, relative: str, flags: int, mode: int = 0) -> int:
    """Require kernel-enforced containment; an unsupported kernel fails closed."""
    relative_path(relative)
    if os.name != 'posix' or os.uname().machine not in {'x86_64', 'aarch64'}:
        raise RuntimeError('Capture requires Linux openat2')
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    how = OpenHow(flags | os.O_CLOEXEC | os.O_NOFOLLOW, mode, 0x08 | 0x04 | 0x02)
    descriptor = libc.syscall(ctypes.c_long(437), ctypes.c_int(directory),
        ctypes.c_char_p(os.fsencode(relative)), ctypes.byref(how), ctypes.sizeof(how))
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), 'Confined capture open failed')
    return descriptor


def identity(value: os.stat_result) -> tuple:
    return value.st_dev, value.st_ino


def stable_identity(value: os.stat_result) -> tuple:
    return identity(value)+(value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class SafeTree:
    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing_fd(os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)) as root:
            self.root_fd = open_beneath(root, self.path.as_posix().lstrip('/') or '.',
                                       os.O_RDONLY | os.O_DIRECTORY)

    def __enter__(self):
        return self

    def __exit__(self, *ignored):
        os.close(self.root_fd)

    def open(self, relative: str, flags: int, mode: int = 0) -> int:
        return open_beneath(self.root_fd, relative, flags, mode)

    @contextmanager
    def fd(self, relative: str, flags: int, mode: int = 0):
        with closing_fd(self.open(relative, flags, mode)) as descriptor:
            yield descriptor

    @contextmanager
    def parent(self, relative: str):
        path = PurePosixPath(relative_path(relative))
        if str(path) == '.':
            raise ValueError('Operation requires an entry below the tree root')
        with self.fd(str(path.parent), os.O_RDONLY | os.O_DIRECTORY) as descriptor:
            yield descriptor, path.name

    def lstat(self, relative: str) -> os.stat_result:
        with self.fd(relative, os.O_PATH) as descriptor:
            return os.fstat(descriptor)

    def require_regular(self, relative: str) -> None:
        if not stat.S_ISREG(self.lstat(relative).st_mode):
            raise ValueError('n8n key and database must be regular files within the captured root')

    def digest(self, relative: str) -> str:
        with self.fd(relative, os.O_RDONLY | os.O_NONBLOCK) as descriptor:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError('Expected a regular captured file')
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1024*1024):
                digest.update(chunk)
            return digest.hexdigest()

    def read(self, relative: str) -> bytes:
        with self.fd(relative, os.O_RDONLY | os.O_NONBLOCK) as descriptor:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError('Expected a regular captured file')
            with os.fdopen(os.dup(descriptor), 'rb') as stream:
                return stream.read()

    def write(self, relative: str, value: bytes) -> None:
        with self.fd(relative, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as descriptor:
            with os.fdopen(os.dup(descriptor), 'wb') as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())

    def mkdir(self, relative: str) -> None:
        with self.parent(relative) as (parent, name):
            os.mkdir(name, mode=0o700, dir_fd=parent)

    def symlink(self, relative: str, target: str) -> None:
        with self.parent(relative) as (parent, name):
            os.symlink(target, name, dir_fd=parent)

    def readlink(self, relative: str) -> str:
        with self.fd(relative, os.O_PATH) as descriptor:
            if not stat.S_ISLNK(os.fstat(descriptor).st_mode):
                raise ValueError('Expected a captured symlink')
            return os.readlink('', dir_fd=descriptor)

    def metadata(self, relative: str) -> dict:
        value = self.lstat(relative)
        if stat.S_ISLNK(value.st_mode):
            # l*xattr does not dereference the final entry. Only the already
            # anchored parent FD is reached through this process's own procfs.
            with self.parent(relative) as (parent, name):
                path = '/proc/self/fd/'+str(parent)+'/'+name
                attrs = {key: base64.b64encode(os.getxattr(path, key, follow_symlinks=False)).decode()
                         for key in os.listxattr(path, follow_symlinks=False)}
                if identity(value) != identity(os.stat(name, dir_fd=parent, follow_symlinks=False)):
                    raise ValueError('Capture entry changed while reading metadata')
        elif stat.S_ISREG(value.st_mode) or stat.S_ISDIR(value.st_mode):
            flags = os.O_RDONLY | (os.O_DIRECTORY if stat.S_ISDIR(value.st_mode) else os.O_NONBLOCK)
            with self.fd(relative, flags) as descriptor:
                if identity(value) != identity(os.fstat(descriptor)):
                    raise ValueError('Capture entry changed while reading metadata')
                attrs = {key: base64.b64encode(os.getxattr(descriptor, key)).decode()
                         for key in os.listxattr(descriptor)}
        else:
            raise ValueError('Unexpected special file in persistent capture')
        return {'uid': value.st_uid, 'gid': value.st_gid, 'mode': stat.S_IMODE(value.st_mode),
                'mtimeNs': value.st_mtime_ns, 'xattrs': attrs}

    def apply_metadata(self, relative: str, row: dict) -> None:
        if stat.S_ISLNK(self.lstat(relative).st_mode):
            with self.parent(relative) as (parent, name):
                os.chown(name, row['uid'], row['gid'], dir_fd=parent, follow_symlinks=False)
                os.utime(name, ns=(row['mtimeNs'], row['mtimeNs']), dir_fd=parent, follow_symlinks=False)
                for key, value in row['xattrs'].items():
                    os.setxattr('/proc/self/fd/'+str(parent)+'/'+name, key,
                                base64.b64decode(value), follow_symlinks=False)
        else:
            with self.fd(relative, os.O_RDONLY | os.O_NONBLOCK) as descriptor:
                os.fchown(descriptor, row['uid'], row['gid'])
                os.fchmod(descriptor, row['mode'])
                os.utime(descriptor, ns=(row['mtimeNs'], row['mtimeNs']))
                for key, value in row['xattrs'].items():
                    os.setxattr(descriptor, key, base64.b64decode(value))

    def walk(self, relative: str = '.'):
        value = self.lstat(relative)
        if relative != '.':
            yield relative
        if stat.S_ISDIR(value.st_mode):
            with self.fd(relative, os.O_RDONLY | os.O_DIRECTORY) as descriptor:
                if identity(value) != identity(os.fstat(descriptor)):
                    raise ValueError('Capture directory changed during traversal')
                names = sorted(os.listdir(descriptor))
                for name in names:
                    yield from self.walk(name if relative == '.' else relative+'/'+name)
                if identity(value) != identity(self.lstat(relative)):
                    raise ValueError('Capture directory changed during traversal')

    def copy_from(self, source: SafeTree, relative: str, destination: str | None = None) -> dict:
        with source.fd(relative, os.O_RDONLY | os.O_NONBLOCK) as descriptor:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('Expected a regular source file')
            row = {'uid': before.st_uid, 'gid': before.st_gid,
                   'mode': stat.S_IMODE(before.st_mode), 'mtimeNs': before.st_mtime_ns,
                   'xattrs': {key: base64.b64encode(os.getxattr(descriptor, key)).decode()
                              for key in os.listxattr(descriptor)}}
            with self.fd(destination or relative, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as output:
                with os.fdopen(os.dup(output), 'wb') as stream:
                    while block := os.read(descriptor, 1024*1024):
                        stream.write(block)
                    stream.flush()
                    os.fsync(stream.fileno())
            if stable_identity(before) != stable_identity(os.fstat(descriptor)):
                raise ValueError('n8n supporting file changed during capture')
            return row


@contextmanager
def closing_fd(descriptor: int):
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def sqlite_task(tree: SafeTree, operation: str, relative: str) -> bytes:
    relative_path(relative)
    result = subprocess.run([sys.executable, '-B', str(Path(__file__).absolute()),
        '--sqlite-child', str(tree.root_fd), operation, relative],
        pass_fds=(tree.root_fd,), stdin=subprocess.DEVNULL, capture_output=True, timeout=150)
    if result.returncode != 0:
        raise RuntimeError('Confined SQLite operation failed')
    return result.stdout


def sqlite_snapshot_file(source: SafeTree, relative: str,
                         destination: SafeTree, target: str) -> None:
    """Write a confined online snapshot without buffering it in the parent."""
    relative_path(relative)
    source.require_regular(relative)
    if source.lstat(relative).st_size > 1024*1024*1024:
        raise ValueError('SQLite source exceeds the admitted 1 GiB memory bound')
    def limits() -> None:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (3*1024**3, 3*1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024**3, 1024**3))
    with destination.fd(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as output:
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).absolute()),
            '--sqlite-child', str(source.root_fd), 'snapshot', relative],
            pass_fds=(source.root_fd,), stdin=subprocess.DEVNULL, stdout=output,
            stderr=subprocess.PIPE, timeout=150, preexec_fn=limits)
        if result.returncode:
            raise RuntimeError('Confined SQLite file snapshot failed')
        os.fsync(output)


def confine(directory: int) -> None:
    if os.geteuid() != 0:
        raise RuntimeError('SQLite confinement requires the root backup service')
    last_cap = int(Path('/proc/sys/kernel/cap_last_cap').read_text())
    os.fchdir(directory)
    os.chroot('.')
    os.chdir('/')
    os.closerange(3, 1048576)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(28, 3, 0, 0, 0) != 0:
        raise RuntimeError('Could not restrict SQLite child privileges')
    for capability in range(last_cap+1):
        if libc.prctl(24, capability, 0, 0, 0) != 0:
            raise RuntimeError('Could not clear SQLite child capability bounds')
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32),
                    ('inheritable', ctypes.c_uint32)]
    # UID/modes in the application snapshot can differ. Only DAC override is
    # retained for those files; chroot/mount/exec privilege recovery is forbidden.
    data = (Data*2)(Data(2, 2, 0), Data(0, 0, 0))
    if libc.capset(ctypes.byref(Header(0x20080522, 0)), ctypes.byref(data)) != 0:
        raise RuntimeError('Could not drop SQLite child capabilities')


def snapshot_connection(source: sqlite3.Connection, target: sqlite3.Connection,
                        progress, *, pages: int = 1024) -> None:
    """Pin one read snapshot so concurrent WAL commits cannot restart copying."""
    source.execute('BEGIN')
    try:
        source.execute('SELECT count(*) FROM sqlite_master').fetchall()
        page_size = int(source.execute('PRAGMA page_size').fetchone()[0])
        target.execute('PRAGMA page_size='+str(page_size))
        source.backup(target, pages=pages, progress=progress, sleep=.05)
    finally:
        source.rollback()


def sqlite_child(directory: int, operation: str, relative: str) -> None:
    relative_path(relative)
    confine(directory)
    if operation == 'snapshot':
        with closing(sqlite3.connect('file:/'+relative+'?mode=ro', uri=True, timeout=30)) as source:
            with closing(sqlite3.connect(':memory:')) as target:
                deadline = time.monotonic()+120
                def progress(status, remaining, total):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Online SQLite snapshot deadline exceeded')
                snapshot_connection(source, target, progress)
                sys.stdout.buffer.write(target.serialize())
        return
    if operation not in {'normalize', 'verify'}:
        raise ValueError('Unknown confined SQLite operation')
    mode = 'rw' if operation == 'normalize' else 'ro'
    with closing(sqlite3.connect('file:/'+relative+'?mode='+mode, uri=True, timeout=30)) as database:
        if operation == 'normalize' and database.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
            raise ValueError('Could not finalize a standalone SQLite snapshot')
        if database.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite database integrity check failed')
        names = [row[0] for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {name: database.execute('SELECT count(*) FROM "'+name.replace('"', '""')+'"').fetchone()[0]
                  for name in names}
    print(json.dumps({'integrityCheck': 'ok', 'tableRowCounts': counts}))


if __name__ == '__main__':
    if len(sys.argv) != 5 or sys.argv[1] != '--sqlite-child':
        raise SystemExit('This module is invoked only by the native capture producer')
    sqlite_child(int(sys.argv[2]), sys.argv[3], sys.argv[4])

