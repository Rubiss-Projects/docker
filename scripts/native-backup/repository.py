#!/usr/bin/env python3
"""Run a fresh Portainer capture, encrypted NAS backup, and verified restore."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

try:
    import fcntl
except ImportError:
    fcntl = None

import portainer


def save(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as output:
        json.dump(value, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def guard_mount(config: dict) -> None:
    target = Path(config['mountTarget'])
    repository = Path(config['repository'])
    rows = json.loads(subprocess.check_output([
        'findmnt', '--json', '--target', str(target), '--output', 'TARGET,SOURCE,FSTYPE,OPTIONS'
    ]))['filesystems']
    if len(rows) != 1:
        raise ValueError('Expected exactly one admitted NAS mount')
    row = rows[0]
    if (row['target'], row['source'], row['fstype']) != (
            str(target), config['mountSource'], config['mountType']):
        raise ValueError('NAS mount identity does not match; local fallback is forbidden')
    if 'rw' not in row['options'].split(','):
        raise ValueError('NAS recovery mount is not writable')
    if not repository.is_dir() or not repository.resolve().is_relative_to(target.resolve()):
        raise ValueError('Repository must exist inside the admitted mount')
    if repository.resolve() == target.resolve():
        raise ValueError('The share root is not a repository directory')
    space = os.statvfs(repository)
    if space.f_bavail * space.f_frsize < config['minimumFreeBytes']:
        raise ValueError('NAS recovery headroom is below policy')


def notify(config: dict, success: bool) -> None:
    """Use the existing human-alert push monitor, keeping its token out of logs."""
    value = Path(config['pushUrlFile']).read_text().strip()
    url = urllib.parse.urlsplit(value)
    if (url.scheme != 'http' or url.hostname != '127.0.0.1' or url.port != 3001
            or not url.path.startswith('/api/push/') or url.query or url.fragment
            or url.username or url.password):
        raise ValueError('Expected a private local Kuma push-monitor URL')
    query = urllib.parse.urlencode({'status': 'up' if success else 'down',
                                   'msg': 'Backup and restore verified' if success else 'Native backup failed; inspect private job receipt'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), portainer.NoRedirect())
    # HTTP exceptions include the token-bearing URL. Replace them before logging.
    try:
        with opener.open(value+'?'+query, timeout=15) as response:
            result = json.load(response)
            if response.status != 200 or result.get('ok') is not True:
                raise ValueError('Push monitor did not accept heartbeat')
    except Exception:
        raise RuntimeError('Backup monitor delivery failed') from None


class Repository:
    def __init__(self, config: dict, directory: Path):
        self.config = config
        self.directory = directory
        self.sequence = 0

    def run(self, *arguments: str) -> str:
        guard_mount(self.config)
        self.sequence += 1
        result = subprocess.run([
            'restic', '--repo', self.config['repository'],
            '--password-file', self.config['passwordFile'], '--no-cache', *arguments
        ], env={**os.environ, 'GODEBUG': 'asyncpreemptoff=1'}, capture_output=True,
            text=True, timeout=self.config['commandTimeoutSeconds'], check=False)
        prefix = self.directory / f'restic-{self.sequence}'
        prefix.with_suffix('.stdout').write_text(result.stdout)
        prefix.with_suffix('.stderr').write_text(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f'Restic step {self.sequence} failed; reconcile retained receipt')
        return result.stdout

    def verify_identity(self) -> None:
        value = json.loads(self.run('cat', 'config'))
        if value['id'] != self.config['repositoryId']:
            raise ValueError('Unexpected encrypted repository identity')

    def retention(self, apply: bool = False) -> dict:
        # One comma-separated filter requires BOTH tags. Separate --tag filters
        # have OR semantics and could select snapshots belonging to another scope.
        output = self.run('forget', '--dry-run', '--json', '--host', 'ben-server',
            '--tag', 'native-recurring,scope=portainer', '--group-by', 'host,tags',
            '--keep-daily', '14', '--keep-weekly', '8', '--keep-monthly', '12')
        groups = json.loads(output)
        removal = set()
        for group in groups:
            for row in group.get('remove') or []:
                if row.get('hostname') != 'ben-server' or set(row.get('tags') or []) != {
                        'native-recurring', 'scope=portainer'}:
                    raise ValueError('Retention plan selected an unowned snapshot')
                if not re.fullmatch('[0-9a-f]{64}', row['id']):
                    raise ValueError('Retention requires complete immutable snapshot IDs')
                removal.add(row['id'])
        result = {'mode': 'apply' if apply else 'dry_run', 'groups': groups,
                  'deletionPerformed': False, 'removedSnapshotIds': []}
        if not apply or not removal:
            return result
        before = json.loads(self.run('snapshots', '--json'))
        by_id = {row['id']: row for row in before}
        for snapshot in removal:
            row = by_id[snapshot]
            if row.get('hostname') != 'ben-server' or set(row.get('tags') or []) != {
                    'native-recurring', 'scope=portainer'}:
                raise ValueError('Retention candidate changed before execution')
        owned = {row['id'] for row in before if row.get('hostname') == 'ben-server'
                 and set(row.get('tags') or []) == {'native-recurring', 'scope=portainer'}}
        if not owned - removal:
            raise ValueError('Retention must preserve a snapshot of this scope')
        # Persist the exact mutation before doing it. Do not re-run broad filters
        # after review: only the already-validated immutable IDs can be forgotten.
        save(self.directory/'retention-execution-intent.json', {
            'removeSnapshotIds': sorted(removal), 'preserveSnapshotIds': sorted(set(by_id)-removal)})
        self.run('forget', *sorted(removal))
        after = {row['id'] for row in json.loads(self.run('snapshots', '--json'))}
        if after != set(by_id)-removal:
            raise ValueError('Repository snapshot inventory changed during retention; reconcile before pruning')
        self.run('prune', '--max-repack-size', '1G')
        self.run('check', '--read-data')
        final = {row['id'] for row in json.loads(self.run('snapshots', '--json'))}
        if final != after:
            raise ValueError('Snapshot inventory changed during prune; reconcile retained receipts')
        result.update(deletionPerformed=True, removedSnapshotIds=sorted(removal),
                      allUnselectedSnapshotsRetained=True, fullPostPruneReadDataCheckPassed=True)
        return result


def run(config: dict) -> dict:
    if fcntl is None:
        raise RuntimeError('Native backup requires Linux file locking')
    if type(config['applyRetention']) is not bool:
        raise ValueError('applyRetention must be a JSON boolean')
    os.umask(0o077)
    state = Path(config['stateDirectory'])
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state/'job.lock').open('a') as lock:
        # An overlapping invocation is not permission to take over a live job.
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (state/'capture-attention.json').exists():
            notify(config, False)
            raise RuntimeError('Reconcile the previous uncertain API capture before another request')
        name = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        directory = state/name
        directory.mkdir(mode=0o700)
        result = {'scope': 'portainer', 'startedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
                  'phase': 'admission', 'success': False, 'containerControls': 0}
        save(directory/'job.json', result)
        started = time.monotonic()
        try:
            repository = Repository(config, directory)
            repository.verify_identity()
            tool = Path(config['bbolt'])
            with tool.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != portainer.BBOLT_SHA256:
                    raise ValueError('Unexpected bbolt verifier binary')
            result['phase'] = 'capture'
            save(directory/'job.json', result)
            capture = directory/'capture'
            proof = portainer.capture(capture, tool)
            result['phase'] = 'encrypted_backup'
            save(directory/'job.json', result)
            output = repository.run('backup', '--json', '--host', 'ben-server',
                '--tag', 'native-recurring', '--tag', 'scope=portainer', str(capture))
            summaries = [value for line in output.splitlines() if (value := json.loads(line)).get('message_type') == 'summary']
            if len(summaries) != 1 or not summaries[0].get('snapshot_id'):
                raise ValueError('Restic did not report one completed snapshot')
            snapshot = summaries[0]['snapshot_id']
            result.update(snapshotId=snapshot, phase='restore_verification')
            save(directory/'job.json', result)
            repository.run('check', '--read-data')
            restored = directory/'restore'
            repository.run('restore', snapshot, '--target', str(restored), '--verify')
            archive = restored / capture.relative_to(capture.anchor) / 'backup.tar.gz'
            with archive.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != proof['archiveSha256']:
                    raise ValueError('Restored archive digest differs from fresh capture')
            restored_proof = portainer.inspect_archive(archive, tool)
            if restored_proof['files'] != proof['files']:
                raise ValueError('Restored database or key files differ from capture')
            retention = repository.retention(apply=config['applyRetention'])
            save(directory/'retention-plan.json', retention)
            result.update(phase='monitor_delivery', encryptedRepositoryCaptureVerified=True,
                          restoreReadbackVerified=True, retentionMode=retention['mode'])
            save(directory/'job.json', result)
            notify(config, True)
            result.update(success=True, phase='complete', elapsedSeconds=round(time.monotonic()-started, 2))
            save(directory/'job.json', result)
            save(state/'latest.json', result)
            return result
        except BaseException as error:
            if result['phase'] == 'capture':
                save(state/'capture-attention.json', {'jobDirectory': str(directory),
                    'reason': 'Capture did not complete; reconcile retained intent and archive before another API request'})
            result.update(phase='failed', failedAtPhase=result['phase'],
                          errorType=type(error).__name__, elapsedSeconds=round(time.monotonic()-started, 2))
            # No exception text: transport errors can contain credential-bearing URLs.
            save(directory/'job.json', result)
            save(state/'latest.json', result)
            try:
                notify(config, False)
            except Exception:
                result['monitorDeliveryFailed'] = True
                save(directory/'job.json', result)
                save(state/'latest.json', result)
            raise RuntimeError('Native backup failed; inspect private job receipt') from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run using the root-owned native backup configuration')
    stat = args.config.stat()
    if stat.st_uid != 0 or stat.st_mode & 0o077:
        parser.error('Backup configuration must be root-owned mode 0600')
    print(json.dumps(run(json.loads(args.config.read_text()))))


if __name__ == '__main__':
    main()
