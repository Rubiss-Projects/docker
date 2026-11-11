"""Restore the exact admitted containers drained by a previous UPS shutdown."""
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import time

from native_ups_guard import ROOT, decision, manifest_lock, sample, write_state


def select_stopped(manifest, current, policy, boot):
    """Validate the whole snapshot before returning any container to start."""
    saved_boot = manifest.get('boot')
    if (manifest.get('version') != 1 or not isinstance(saved_boot, str)
            or not re.fullmatch('[a-z0-9-]{1,64}', saved_boot) or saved_boot == boot):
        raise ValueError('UPS recovery requires a previous-boot manifest')
    saved = manifest.get('containers')
    if not isinstance(saved, list) or len(saved) > 1000:
        raise ValueError('Invalid UPS recovery container list')
    by_id = {c['Id']: c for c in current}
    seen = set()
    stopped = []
    for item in saved:
        cid = item.get('id', '')
        if not re.fullmatch('[0-9a-f]{64}', cid) or cid in seen:
            raise ValueError('Invalid or duplicate saved container identity')
        seen.add(cid)
        project, service = item.get('project'), item.get('service')
        if service not in policy.get('stacks', {}).get(project, {}).get('services', {}):
            raise ValueError('Saved service is no longer admitted')
        c = by_id.get(cid)
        if c is None or c.get('Image') != item.get('image'):
            raise ValueError('Saved container is missing or its image changed')
        labels = c.get('Config', {}).get('Labels') or {}
        if (labels.get('com.docker.compose.project') != project
                or labels.get('com.docker.compose.service') != service):
            raise ValueError('Saved Compose ownership changed')
        if not c['State']['Running']:
            stopped.append(cid)
    return stopped


def load_manifest(path, *, private=True):
    parent = path.parent.stat()
    if path.parent.resolve() != path.parent or parent.st_uid != 0 or parent.st_mode & 0o022:
        raise ValueError('UPS recovery requires a root-controlled state/policy directory')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor) as stream:
        info = os.fstat(stream.fileno())
        forbidden = 0o077 if private else 0o022
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & forbidden or info.st_size > 1024 * 1024:
            raise ValueError('UPS manifest must be a private root-owned regular file')
        return json.load(stream)


def require_no_shutdown_intent(boot):
    """Hold if this boot has already committed to a protective shutdown."""
    intent = ROOT / 'shutdown-intent.json'
    if intent.exists() and load_manifest(intent).get('boot') == boot:
        raise ValueError('UPS shutdown is already committed on this boot')


def require_online(boot):
    require_no_shutdown_intent(boot)
    if decision(sample(), 0) != 'online':
        raise ValueError('UPS recovery held until utility power is confirmed')


def wait_for_local_ups(boot):
    """Allow the local USB driver up to 45 seconds to publish fresh utility status."""
    if os.environ.get('NATIVE_UPS_HOST') != '127.0.0.1':
        return
    deadline = time.monotonic() + 45
    while True:
        require_no_shutdown_intent(boot)
        try:
            outcome = decision(sample(), 0)
        except (OSError, ValueError):
            outcome = 'unknown'
        if outcome == 'online':
            return
        if outcome != 'unknown':
            raise ValueError('UPS recovery held: local UPS is not on utility power')
        if time.monotonic() >= deadline:
            raise ValueError('Local UPS readiness timed out; retain recovery manifest')
        time.sleep(1)


def main():
    if os.geteuid() != 0 or socket.gethostname() != 'ben-server' or ROOT.resolve() != ROOT:
        raise ValueError('UPS recovery is restricted to the admitted native host')
    path = ROOT / 'restore-pending.json'
    if not path.exists():
        return
    lock_fd = os.open(ROOT / 'restore.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = load_manifest(path)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        wait_for_local_ups(boot)
        require_online(boot)
        ids = [c['id'] for c in manifest['containers']]
        if not ids or any(not re.fullmatch('[0-9a-f]{64}', cid) for cid in ids):
            raise ValueError('UPS recovery requires exact saved container IDs')
        current = json.loads(subprocess.check_output(['docker', 'inspect', *ids], timeout=15))
        # The same root-controlled policy and mount admission used by deployment
        # must pass before an existing container can regain writer ownership.
        policy = load_manifest(Path('/etc/docker-ops/native-policy.json'), private=False)
        if policy.get('schemaVersion') != 1 or policy.get('released') is not True:
            raise ValueError('Native deployment policy has not been released')
        stopped = select_stopped(manifest, current, policy, boot)
        projects = sorted({c['project'] for c in manifest['containers']})
        subprocess.run(['runuser', '-u', 'rubiss', '--', 'python3', '-B',
                        '/srv/Docker/scripts/native-deploy/compose.py', '--repo', '/srv/Docker',
                        '--admit', *projects], check=True, timeout=120)
        priority = {'socket-proxy': 0, 'uptime-kuma': 1, 'plex': 2, 'swag': 4}
        saved_by_id = {c['id']: c for c in manifest['containers']}
        stopped.sort(key=lambda cid: priority.get(saved_by_id[cid]['project'], 3))
        for cid in stopped:
            require_online(boot)
            subprocess.run(['docker', 'start', cid], check=True, timeout=30,
                           stdout=subprocess.DEVNULL)
        after = json.loads(subprocess.check_output(['docker', 'inspect', *ids], timeout=15))
        if select_stopped(manifest, after, policy, boot):
            raise ValueError('UPS recovery has containers still stopped')
        with manifest_lock():
            require_online(boot)
            if load_manifest(path) != manifest:
                raise ValueError('Pending UPS recovery changed; retain it for reconciliation')
            write_state(ROOT / 'restore-result.json',
                        {'boot': boot, 'shutdownBoot': manifest['boot'],
                         'startedContainers': len(stopped), 'recreatedContainers': 0})
            path.rename(ROOT / ('restore-completed-' + manifest['boot'] + '.json'))


if __name__ == '__main__':
    main()
