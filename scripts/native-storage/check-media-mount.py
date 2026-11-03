#!/usr/bin/env python3
"""Read-only Docker prestart admission; never create a missing media directory."""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


class AdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class Mount:
    mount_id: int
    target: str
    source: str
    fstype: str
    options: frozenset[str]
    super_options: frozenset[str]


@dataclass(frozen=True)
class Policy:
    mountpoint: str
    source: str
    access: str
    required_roots: tuple[str, ...]

    @classmethod
    def load(cls, data: object) -> "Policy":
        keys = {"mountpoint", "source", "access", "required_roots"}
        if not isinstance(data, dict) or set(data) != keys:
            raise AdmissionError("Policy must contain exactly the documented fields")
        mountpoint, source, access, roots = (data[k] for k in ("mountpoint", "source", "access", "required_roots"))
        if not isinstance(mountpoint, str) or not mountpoint.startswith('/') or str(PurePosixPath(mountpoint)) != mountpoint or '..' in PurePosixPath(mountpoint).parts or mountpoint == '/':
            raise AdmissionError("Mountpoint must be an absolute normalized non-root path")
        if not isinstance(source, str) or ':/' not in source or any(c.isspace() for c in source):
            raise AdmissionError("Source must be the exact reviewed NFS server:/export")
        if access not in ('rw', 'ro'):
            raise AdmissionError("Access must be rw or ro")
        if not isinstance(roots, list) or not roots or not all(isinstance(r, str) and r and not r.startswith('/') and '..' not in PurePosixPath(r).parts and '\\' not in r and '\0' not in r and str(PurePosixPath(r)) == r for r in roots):
            raise AdmissionError("Required roots must be normalized relative paths without traversal")
        return cls(mountpoint, source, access, tuple(roots))


def decode_mount_field(value: str) -> str:
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)


def parse_mountinfo(text: str) -> list[Mount]:
    mounts = []
    for line in text.splitlines():
        before, separator, after = line.partition(' - ')
        # WSL 9p super-options may contain literal spaces in a Windows path.
        fields, fs = before.split(), after.split(maxsplit=2)
        if not separator or len(fields) < 6 or len(fs) != 3:
            raise AdmissionError("Malformed kernel mount record")
        if not fields[0].isdecimal() or int(fields[0]) <= 0:
            raise AdmissionError("Malformed kernel mount ID")
        mounts.append(Mount(int(fields[0]), decode_mount_field(fields[4]), decode_mount_field(fs[1]), fs[0], frozenset(fields[5].split(',')), frozenset(fs[2].split(','))))
    return mounts


def validate_mount(policy: Policy, mounts: list[Mount]) -> Mount:
    matches = [m for m in mounts if m.target == policy.mountpoint]
    if len(matches) != 1:
        raise AdmissionError("Expected exactly one mount at the required mountpoint")
    mount = matches[0]
    if mount.fstype not in ('nfs', 'nfs4') or mount.source != policy.source:
        raise AdmissionError("Wrong filesystem or NFS source")
    combined = mount.options | mount.super_options
    if policy.access not in mount.options or policy.access not in mount.super_options:
        raise AdmissionError("Mount access does not match the reviewed policy")
    if 'hard' not in combined or combined & {'soft', 'softerr', 'softreval'}:
        raise AdmissionError("A hard NFS mount is required")
    if not combined & {'vers=4.1', 'vers=4.2'} or 'proto=tcp' not in combined:
        raise AdmissionError("Expected tested NFS 4.1/4.2 over TCP")
    for other in mounts:
        if other.target.startswith(policy.mountpoint + '/'):
            raise AdmissionError("Unexpected nested mount inside the media tree")
    return mount


def visible_mount_id(path: str) -> int:
    # fdinfo identifies the mount reached by pathname lookup, including overmounts.
    if not hasattr(os, 'O_PATH'):
        raise AdmissionError("Mount visibility admission requires Linux O_PATH")
    descriptor = os.open(path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = Path(f'/proc/self/fdinfo/{descriptor}').read_text()
        ids = re.findall(r'^mnt_id:\s*(\d+)\s*$', info, re.MULTILINE)
        if len(ids) != 1:
            raise AdmissionError("Cannot identify the visible media mount")
        return int(ids[0])
    finally:
        os.close(descriptor)


def verify_mount_visibility(policy: Policy, mount: Mount) -> None:
    if visible_mount_id(policy.mountpoint) != mount.mount_id:
        raise AdmissionError("Reviewed NFS mount is hidden at the media path")


def probe_roots(policy: Policy) -> None:
    # Only touch NAS paths after mount identity has passed. lstat rejects redirects.
    for root in policy.required_roots:
        path = Path(policy.mountpoint)
        for component in ('.', *PurePosixPath(root).parts):
            path = path / component
            mode = path.lstat().st_mode
            if not stat.S_ISDIR(mode):
                raise AdmissionError("A required root is missing, redirected or not a directory")
            if not os.access(path, os.R_OK | os.X_OK, effective_ids=True):
                raise AdmissionError("Daemon cannot read/search a required root")


def check(policy: Policy, mountinfo: str) -> None:
    mount = validate_mount(policy, parse_mountinfo(mountinfo))
    verify_mount_visibility(policy, mount)
    probe_roots(policy)
    verify_mount_visibility(policy, mount)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    try:
        policy = Policy.load(json.loads(args.config.read_text()))
        check(policy, Path('/proc/self/mountinfo').read_text())
    except (OSError, ValueError, TypeError) as exc:
        print(f'Media startup held: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    print('Media mount identity and required directory access verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
