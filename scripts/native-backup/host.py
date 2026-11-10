"""Full native host state and the current deployment bootstrap recovery set."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile

from confined_files import SafeTree
from host_files import capture_tree, inspect_tree

ROOTS = [Path(p) for p in ['/home/rubiss', '/etc', '/usr/local', '/opt',
    '/var/lib/tailscale', '/var/lib/caddy-plex', '/var/lib/nas-migration-ups',
    '/var/lib/systemd/linger', '/var/spool/cron', '/var/lib/dpkg/status']]
REPOSITORY = Path('/srv/Docker')
GIT = ['runuser', '-u', 'rubiss', '--', 'git', '--no-optional-locks', '-C', str(REPOSITORY)]
METADATA = ('uid', 'gid', 'mode', 'mtimeNs', 'xattrs')
HOST_STATE = Path('/var/lib/native-backup/host')
MAX_CAPTURE_BYTES = 40*1024**3


def command(args: list[str], *, input: bytes | None = None) -> bytes:
    value = subprocess.run(args, input=input, capture_output=True, timeout=120)
    if value.returncode:
        raise RuntimeError('Host backup command failed; inspect private job state')
    return value.stdout


def runtime() -> list[dict]:
    ids = command(['docker', 'ps', '-q']).decode().split()
    rows = json.loads(command(['docker', 'inspect', *ids]))
    if len(rows) != 49 or not all(r['State']['Running'] and r['RestartCount'] == 0
            and r['State'].get('Health', {}).get('Status') in [None, 'healthy'] for r in rows):
        raise ValueError('Native host runtime requires fresh admission')
    return rows


def epoch(rows: list[dict]) -> dict:
    return {r['Id']: [r['State']['StartedAt'], r['RestartCount'], r['Image'],
                     r['HostConfig'], r['Config'], r['NetworkSettings']] for r in rows}


def clean_head() -> str:
    if command(GIT+['branch', '--show-current']).strip() != b'main' or command(
            GIT+['status', '--porcelain=v1', '--untracked-files=all']).strip():
        raise ValueError('Host bootstrap capture requires a clean canonical main')
    return command(GIT+['rev-parse', 'HEAD']).decode().strip()


def private_json(tree: SafeTree, name: str, value) -> None:
    tree.write(name, json.dumps(value, indent=2).encode())


def tree_manifest() -> dict:
    result = {}
    for row in command(GIT+['ls-tree', '-r', '--long', '-z', 'HEAD']).split(b'\0'):
        if not row:
            continue
        fields, path = row.split(b'\t', 1)
        mode, kind, digest, size = fields.split()
        name = path.decode()
        if kind != b'blob' or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
            raise ValueError('Unsupported Git source tree entry')
        result[name] = {'mode': mode.decode(), 'blobSha1': digest.decode(), 'bytes': int(size)}
    if not result:
        raise ValueError('Git source tree is empty')
    return result


def archive_manifest(raw: dict, copies: dict, overlays: list[Path]) -> dict:
    """Git archives apply git-crypt's export filter; bind those bytes to copies."""
    result = {name: dict(row) for name, row in raw.items()}
    by_source = {row['source']: (name, row) for name, row in copies.items()}
    for path in overlays:
        relative = path.relative_to(REPOSITORY).as_posix()
        if relative not in result or str(path) not in by_source:
            raise ValueError('Protected Git export has no paired bootstrap copy')
        name, copied = by_source[str(path)]
        result[relative].update(gitCryptProtected=True, exportedBytes=copied['bytes'],
            exportedSha256=copied['sha256'], sourceCopyName=name)
    return result


def inspect_archive(tree: SafeTree, manifest: dict) -> None:
    seen = set()
    with tree.fd('source-tree.tar', os.O_RDONLY) as descriptor:
        with os.fdopen(os.dup(descriptor), 'rb') as stream, tarfile.open(fileobj=stream) as archive:
            for member in archive:
                if member.isdir():
                    continue
                if member.name not in manifest or member.name in seen or not (member.isfile() or member.issym()):
                    raise ValueError('Git source archive entry differs')
                seen.add(member.name)
                row = manifest[member.name]
                if member.issym() != (row['mode'] == '120000'):
                    raise ValueError('Git source archive entry type differs')
                expected_size = row.get('exportedBytes', row['bytes'])
                if member.isfile() and (member.size != expected_size or member.size > 1024**3):
                    raise ValueError('Git source archive entry size differs')
                data = archive.extractfile(member).read() if member.isfile() else member.linkname.encode()
                if row.get('gitCryptProtected') is True:
                    name = row['sourceCopyName']
                    if not re.fullmatch(r'f[0-9]{3,}', name):
                        raise ValueError('Invalid protected Git export copy identity')
                    tree.require_regular('files/'+name)
                    if (len(data) != expected_size or hashlib.sha256(data).hexdigest() != row['exportedSha256']
                            or tree.digest('files/'+name) != row['exportedSha256']):
                        raise ValueError('Protected Git export differs from captured overlay')
                elif len(data) != row['bytes'] or hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() != row['blobSha1']:
                    raise ValueError('Git source archive blob differs')
    if seen != set(manifest):
        raise ValueError('Git source archive is incomplete')


def protected_overlays() -> list[Path]:
    tracked = command(GIT+['ls-files', '-z'])
    fields = command(GIT+['check-attr', '-z', '--stdin', 'filter'], input=tracked).split(b'\0')[:-1]
    if len(fields) % 3:
        raise ValueError('Unexpected Git attribute output')
    paths = [REPOSITORY/fields[i].decode() for i in range(0, len(fields), 3) if fields[i+2] == b'git-crypt']
    if not paths:
        raise ValueError('Protected deployment overlays are missing')
    return paths


def bootstrap_files(rows: list[dict], overlays: list[Path]) -> list[Path]:
    selected = set(overlays)
    for relative in ['.git/HEAD', '.git/config', '.git/packed-refs', '.git/refs/heads/main']:
        path = REPOSITORY/relative
        if path.is_file():
            selected.add(path)
    prefixes = [Path(p) for p in ['/srv/Docker', '/etc', '/usr/local', '/opt', '/usr/share/zoneinfo']]
    for row in rows:
        values = [v for v in (row['Config'].get('Labels') or {}).get('com.docker.compose.project.config_files', '').split(',') if v]
        values += [m['Source'] for m in row['Mounts'] if m['Type'] == 'bind' and Path(m['Source']).is_file()]
        for value in values:
            path = Path(value).resolve(strict=True)
            migration = any(p.parent == Path('/var/lib') and (p.name == 'nas-migration' or p.name.startswith('nas-migration-')) for p in path.parents)
            if not any(path.is_relative_to(p) for p in prefixes) and not migration:
                raise ValueError('Unadmitted bootstrap configuration path')
            if not path.is_file():
                raise ValueError('Compiled bootstrap configuration is missing')
            selected.add(path)
    return sorted(selected)


def capture(destination: Path) -> dict:
    if os.geteuid() != 0:
        raise RuntimeError('Host backup requires the root backup service')
    os.umask(0o077)
    if 'OL' not in command(['upsc', 'qnapups@192.168.50.91', 'ups.status']).decode().split():
        raise ValueError('Host backup requires confirmed utility power')
    head = clean_head();before = runtime();overlays = protected_overlays()
    with SafeTree(destination.parent) as parent:
        parent.mkdir(destination.name)
    with SafeTree(destination) as job:
        private_json(job, 'intent.json', {'at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'canonicalHead': head, 'runtimeContainers': len(before), 'sourceControls': 0})
        job.mkdir('trees');job.mkdir('root-proofs');job.mkdir('bootstrap');job.mkdir('bootstrap/files')
    roots = list(ROOTS)
    key_root = REPOSITORY/'.git/git-crypt'
    if not key_root.is_dir():
        raise ValueError('Git-crypt recovery key directory is missing')
    roots.append(key_root)
    optional = [Path(p) for p in ['/root/.docker', '/root/.ssh', '/root/.config/gh']]
    roots.extend(p for p in optional if p.exists())
    captures = {}
    remaining = MAX_CAPTURE_BYTES
    for index, root in enumerate(roots):
        alias = f'r{index:03d}'
        with SafeTree(destination/'trees') as trees:
            trees.mkdir(alias)
        if root.is_dir():
            proof = capture_tree(root, destination/'trees'/alias, byte_budget=remaining)
        else:
            proof = capture_tree(root.parent, destination/'trees'/alias, root.name, byte_budget=remaining)
        captures[alias] = {'source': str(root), 'proof': proof}
        with SafeTree(destination/'root-proofs') as checkpoints:
            private_json(checkpoints, alias+'.json', captures[alias])
        remaining -= sum(r.get('bytes', 0) for r in proof['entries'].values())
    key_files = sum(r['kind'] == 'file' and r['bytes'] > 0 for r in captures[f'r{len(ROOTS):03d}']['proof']['entries'].values())
    if not key_files:
        raise ValueError('Git-crypt recovery key files are missing')
    # Required live T3 state and provider authentication are part of the full
    # host roots, not inferred from package files or an obsolete migration copy.
    home = captures['r000']['proof']
    if '.t3/userdata/statev2.sqlite' not in home['sqliteDatabases'] or not home['entries'].get('.codex/auth.json', {}).get('bytes'):
        raise ValueError('Required native T3 database or provider authentication is missing')
    selected = bootstrap_files(before, overlays)
    files = {}
    with SafeTree(destination/'bootstrap/files') as target:
        for index, path in enumerate(selected):
            name = f'f{index:03d}'
            with SafeTree(path.parent) as source:
                source.require_regular(path.name)
                if source.lstat(path.name).st_size > remaining:
                    raise ValueError('Bootstrap files exceed the host byte budget')
                metadata = target.copy_from(source, path.name, name)
                target.apply_metadata(name, metadata)
                digest = target.digest(name)
            files[name] = {'source': str(path), **metadata, 'bytes': target.lstat(name).st_size, 'sha256': digest}
            remaining -= files[name]['bytes']
            if remaining < 0:
                raise ValueError('Bootstrap file grew beyond its admitted byte budget')
    with SafeTree(destination/'bootstrap') as bootstrap:
        private_json(bootstrap, 'files-manifest.private.json', files)
    manifest = archive_manifest(tree_manifest(), files, overlays)
    if sum(r['bytes'] for r in manifest.values())+1024*len(manifest)+10240 > min(remaining, 1024**3):
        raise ValueError('Git source archive exceeds its admitted byte budget')
    with SafeTree(destination/'bootstrap') as bootstrap:
        private_json(bootstrap, 'runtime-containers.private.json', before)
        private_json(bootstrap, 'runtime-images.private.json', json.loads(command(['docker', 'image', 'inspect', *sorted({r['Image'] for r in before})])))
        volumes = sorted({m['Name'] for r in before for m in r['Mounts'] if m['Type'] == 'volume'})
        networks = sorted({n for r in before for n in r['NetworkSettings']['Networks']})
        private_json(bootstrap, 'volume-definitions.private.json', json.loads(command(['docker', 'volume', 'inspect', *volumes])))
        private_json(bootstrap, 'network-definitions.private.json', json.loads(command(['docker', 'network', 'inspect', *networks])))
        bootstrap.write('installed-packages.tsv', command(['dpkg-query', '-W', '-f=${Package}\t${Version}\t${Architecture}\n']))
        with bootstrap.fd('source-tree.tar', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as output:
            result = subprocess.run(GIT+['archive', '--format=tar', 'HEAD'], stdout=output, stderr=subprocess.PIPE, timeout=120)
            if result.returncode:
                raise RuntimeError('Git source archive failed')
            os.fsync(output)
        inspect_archive(bootstrap, manifest)
        private_json(bootstrap, 'source-tree-manifest.private.json', manifest)
        generated = {n: {**bootstrap.metadata(n), 'bytes': bootstrap.lstat(n).st_size, 'sha256': bootstrap.digest(n)}
            for n in bootstrap.walk() if stat.S_ISREG(bootstrap.lstat(n).st_mode)}
    # Overlays can rotate without replacing a running container. Require the
    # copies to remain current through the complete host/bootstrap checkpoint.
    for row in files.values():
        path = Path(row['source'])
        with SafeTree(path.parent) as source:
            if source.digest(path.name) != row['sha256']:
                raise ValueError('Bootstrap configuration changed during host capture')
    if clean_head() != head or epoch(runtime()) != epoch(before):
        raise ValueError('Native deployment changed during host capture')
    proof = {'at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'method': 'full_host_online_sqlite_and_current_deployment_bootstrap',
        'canonicalHead': head, 'trees': captures, 'bootstrapFiles': files,
        'generatedBootstrapFiles': generated, 'sourceTreeManifest': manifest,
        'protectedOverlays': len(overlays), 'runtimeContainers': len(before),
        'optionalAbsentRoots': [str(p) for p in optional if not p.exists()],
        'individualDatabaseSnapshotsNotCrossDatabaseAtomic': True,
        'serviceAndPackageReinstallationMustPrecedeSelectiveRestore': True,
        'sourceControls': 0, 'encryptedRepositoryCapturePending': True}
    with SafeTree(destination) as job:
        private_json(job, 'capture.json', proof)
    return proof


def guard_state(state: Path) -> None:
    if state != HOST_STATE or state.resolve() != state or state.stat().st_uid != 0 or state.stat().st_mode & 0o077:
        raise ValueError('Unexpected private host backup state directory')


def guard_local_space(state: Path) -> None:
    guard_state(state)
    if shutil.disk_usage(state).free < 100*1024**3:
        raise ValueError('Host backup requires at least 100 GiB of local headroom')


def cleanup_verified_payloads(state: Path, current: Path, repository) -> dict:
    """Keep current + two earlier payload pairs; only erase proven NAS copies.

    Job receipts remain. Failed/unknown jobs, original migration archives and
    other producers are never candidates, and captured symlinks are not followed.
    """
    guard_state(state)
    if current.parent != state or not shutil.rmtree.avoids_symlink_attacks:
        raise ValueError('Host cleanup requires an anchored private job directory')
    completed = []
    for directory in state.iterdir():
        if directory == current or not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}', directory.name):
            continue
        entry = directory.lstat()
        if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != 0 or entry.st_mode & 0o077:
            continue
        with SafeTree(directory) as job:
            try:
                row = json.loads(job.read('job.json'))
            except FileNotFoundError:
                continue
        if (row.get('scope') == 'host' and row.get('success') is True and row.get('phase') == 'complete'
                and row.get('encryptedRepositoryCaptureVerified') is True and row.get('restoreReadbackVerified') is True
                and re.fullmatch('[0-9a-f]{64}', row.get('snapshotId', ''))):
            completed.append((directory, row))
    candidates = sorted(completed, key=lambda value: value[0].name, reverse=True)[2:]
    if not candidates:
        return {'removedPayloadJobs': [], 'unprovenPayloadJobsRetained': []}
    snapshots = {r['id']: r for r in json.loads(repository.run('snapshots', '--json'))}
    removed = [];retained = []
    for directory, row in candidates:
        with SafeTree(directory) as job:
            names = []
            for name in ['capture', 'restore']:
                try:
                    entry = job.lstat(name)
                except FileNotFoundError:
                    continue
                if not stat.S_ISDIR(entry.st_mode):
                    raise ValueError('Host cleanup payload is not a directory')
                names.append(name)
            if not names:
                continue
            snapshot = snapshots.get(row['snapshotId'], {})
            if (snapshot.get('hostname') != 'ben-server' or set(snapshot.get('tags', [])) != {'native-recurring', 'scope=host'}
                    or snapshot.get('paths') != [str(directory/'capture')]):
                retained.append(directory.name)
                continue
            try:
                job.lstat('payload-removed.json')
            except FileNotFoundError:
                pass
            else:
                raise ValueError('Previously cleaned host payload unexpectedly reappeared')
            for name in names:
                shutil.rmtree(name, dir_fd=job.root_fd)
            private_json(job, 'payload-removed.json', {'at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'snapshotId': row['snapshotId'], 'verifiedEncryptedNasCopyRetained': True})
            removed.append(directory.name)
    return {'removedPayloadJobs': removed, 'unprovenPayloadJobsRetained': retained}


def inspect_capture(destination: Path) -> dict:
    with SafeTree(destination) as job:
        proof = json.loads(job.read('capture.json'))
    mandatory = {f'r{i:03d}': str(root) for i, root in enumerate([*ROOTS, REPOSITORY/'.git/git-crypt'])}
    optional = {'/root/.docker', '/root/.ssh', '/root/.config/gh'}
    if (proof.get('method') != 'full_host_online_sqlite_and_current_deployment_bootstrap'
            or proof.get('runtimeContainers') != 49 or not proof.get('protectedOverlays')
            or any(proof.get('trees', {}).get(alias, {}).get('source') != root for alias, root in mandatory.items())):
        raise ValueError('Host recovery does not cover the admitted full roots and bootstrap')
    sources = [r['source'] for r in proof['trees'].values()]
    if (len(sources) != len(set(sources)) or not set(proof['optionalAbsentRoots']).issubset(optional)
            or set(sources)-set(mandatory.values()) != optional-set(proof['optionalAbsentRoots'])):
        raise ValueError('Host recovery contains unexpected or missing optional roots')
    home = proof['trees']['r000']['proof']
    if '.t3/userdata/statev2.sqlite' not in home['sqliteDatabases'] or not home['entries'].get('.codex/auth.json', {}).get('bytes'):
        raise ValueError('Host recovery lacks required T3 state or provider authentication')
    keys = proof['trees'][f'r{len(ROOTS):03d}']['proof']['entries']
    if not any(r['kind'] == 'file' and r.get('bytes', 0) > 0 for r in keys.values()):
        raise ValueError('Host recovery lacks Git-crypt key files')
    with SafeTree(destination/'trees') as trees:
        with trees.fd('.', os.O_RDONLY | os.O_DIRECTORY) as descriptor:
            if set(os.listdir(descriptor)) != set(proof['trees']):
                raise ValueError('Host recovery tree inventory differs')
    with SafeTree(destination/'root-proofs') as checkpoints:
        if set(checkpoints.walk()) != {alias+'.json' for alias in proof['trees']}:
            raise ValueError('Host root checkpoint inventory differs')
        for alias, row in proof['trees'].items():
            if json.loads(checkpoints.read(alias+'.json')) != row:
                raise ValueError('Host root checkpoint differs from complete manifest')
    for alias, row in proof['trees'].items():
        if not alias.startswith('r') or len(alias) != 4 or not alias[1:].isdigit():
            raise ValueError('Invalid host recovery tree identity')
        inspect_tree(destination/'trees'/alias, row['proof'])
    with SafeTree(destination/'bootstrap/files') as files:
        if set(files.walk()) != set(proof['bootstrapFiles']):
            raise ValueError('Bootstrap file inventory differs')
        for name, row in proof['bootstrapFiles'].items():
            files.require_regular(name)
            if files.lstat(name).st_size != row['bytes'] or files.digest(name) != row['sha256'] or files.metadata(name) != {k: row[k] for k in METADATA}:
                raise ValueError('Bootstrap file or metadata differs')
    with SafeTree(destination/'bootstrap') as bootstrap:
        if json.loads(bootstrap.read('files-manifest.private.json')) != proof['bootstrapFiles']:
            raise ValueError('Bootstrap file mapping checkpoint differs')
        if json.loads(bootstrap.read('source-tree-manifest.private.json')) != proof['sourceTreeManifest']:
            raise ValueError('Source archive mapping checkpoint differs')
        if sum(r.get('gitCryptProtected') is True for r in proof['sourceTreeManifest'].values()) != proof['protectedOverlays']:
            raise ValueError('Protected source archive coverage differs')
        if set(bootstrap.walk()) != {'files'} | set(proof['generatedBootstrapFiles']):
            raise ValueError('Bootstrap tree contains unexpected entries')
        regular = {n for n in bootstrap.walk() if stat.S_ISREG(bootstrap.lstat(n).st_mode)}
        if regular != set(proof['generatedBootstrapFiles']):
            raise ValueError('Generated bootstrap inventory differs')
        for name, row in proof['generatedBootstrapFiles'].items():
            if (bootstrap.lstat(name).st_size != row['bytes'] or bootstrap.digest(name) != row['sha256']
                    or bootstrap.metadata(name) != {k: row[k] for k in METADATA}):
                raise ValueError('Generated bootstrap content differs')
        inspect_archive(bootstrap, proof['sourceTreeManifest'])
    return proof
