#!/usr/bin/env python3
"""Apply the accepted Linux wiring to current repository Compose definitions."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

POLICY = Path('/etc/docker-ops/native-policy.json')
STATE = Path('/var/lib/docker-ops/compiled')
PROTECTED_FIELDS = frozenset({
    'volumes', 'network_mode', 'networks', 'ports', 'extra_hosts', 'entrypoint',
    'command', 'security_opt', 'stop_signal', 'stop_grace_period', 'user',
    'read_only', 'tmpfs', 'mem_limit', 'memswap_limit', 'pids_limit', 'cap_drop',
    'cap_add', 'working_dir', 'profiles', 'build', 'deploy', 'cpuset', 'devices',
    'privileged', 'pid', 'ipc', 'container_name',
})


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def field_value(service: dict, key: str) -> dict:
    return {'present': key in service, 'value': service.get(key)}


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate policy key')
        result[key] = value
    return result


def load_policy(path: Path) -> dict:
    if path.resolve() != path:
        raise ValueError('Native policy must not traverse symlinks')
    parent = path.parent.stat()
    if parent.st_uid != 0 or parent.st_mode & 0o022:
        raise ValueError('Native policy directory must be controlled by root')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Native policy must be a root-owned protected regular file')
        raw = os.read(descriptor, 1024*1024+1)
        if len(raw) > 1024*1024:
            raise ValueError('Native policy exceeds its size limit')
        policy = json.loads(raw, object_pairs_hook=unique_object)
    finally:
        os.close(descriptor)
    if policy.get('schemaVersion') != 1 or policy.get('released') is not True:
        raise ValueError('Native deployment has not been released')
    if not isinstance(policy.get('stacks'), dict) or not policy['stacks']:
        raise ValueError('Native deployment requires explicit accepted stacks')
    return policy


def compile_recipe(source: dict, accepted: dict) -> tuple[dict, set[str]]:
    """Allow ordinary source updates while refusing unreviewed host-wiring changes."""
    if set(source['services']) != set(accepted['services']):
        raise ValueError('Compose service identities differ from native acceptance')
    resources = {key: source.get(key, {}) for key in ['volumes', 'networks']}
    if digest(resources) != accepted['sourceResourcesSha256']:
        raise ValueError('Compose storage or network definitions changed since native acceptance')
    output = copy.deepcopy(source)
    local_images = set()
    for name, rule in accepted['services'].items():
        service = output['services'][name]
        if set(rule['fields']) != PROTECTED_FIELDS:
            raise ValueError('Native service rule lacks complete protected-field coverage')
        for key, change in rule['fields'].items():
            if digest(field_value(service, key)) != change['sourceSha256']:
                raise ValueError('A protected native Compose field changed: '+name+'/'+key)
            if change['present'] is True:
                service[key] = copy.deepcopy(change['value'])
            elif change['present'] is False:
                service.pop(key, None)
            else:
                raise ValueError('Invalid native field presence')
        image = service.get('image', '')
        if not isinstance(image, str) or re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', image) is None:
            raise ValueError('Native source images must remain pinned to registry digests')
        if image == rule['image']['source']:
            local = rule['image']['local']
            if re.fullmatch(r'sha256:[0-9a-f]{64}', local) is None:
                raise ValueError('Invalid accepted local image identity')
            service['image'] = local
            service['pull_policy'] = 'never'
            local_images.add(name)
        for key in rule.get('removeLabels', []):
            service.get('labels', {}).pop(key, None)
        for volume in service.get('volumes', []):
            if volume['type'] == 'bind':
                volume.setdefault('bind', {})['create_host_path'] = False
    for key in ['volumes', 'networks']:
        if accepted['resources'].get(key):
            output[key] = copy.deepcopy(accepted['resources'][key])
        else:
            output.pop(key, None)
    return output, local_images


def capture(command: list[str], *, cwd: Path | None = None) -> bytes:
    result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=60)
    if result.returncode:
        # Docker/renderer errors may contain expanded secrets.
        raise RuntimeError('Native deployment inspection failed; no application operation was admitted')
    return result.stdout


def render_source(repo: Path, stack: str) -> dict:
    directory = repo/stack
    if re.fullmatch(r'[a-z0-9][a-z0-9_-]*', stack) is None or directory.resolve() != directory:
        raise ValueError('Invalid native stack directory')
    command = ['docker', 'compose', '--profile', '*', '--project-name', stack,
               '--project-directory', str(directory)]
    for name in ['.env', '.env.secret']:
        if (directory/name).is_file():
            command += ['--env-file', str(directory/name)]
    return json.loads(capture(command+['-f', str(directory/'docker-compose.yml'), 'config', '--format', 'json']))


def validate_resources(recipe: dict, local_images: set[str], identities: dict) -> None:
    for name in local_images:
        image = recipe['services'][name]['image']
        row = json.loads(capture(['docker', 'image', 'inspect', image]))[0]
        if row['Id'] != image or row['Os'] != 'linux' or row['Architecture'] != 'amd64':
            raise ValueError('Accepted native image is missing or has a different platform')
    volumes = recipe.get('volumes', {})
    networks = recipe.get('networks', {})
    for service in recipe['services'].values():
        for mount in service.get('volumes', []):
            if mount['type'] == 'bind':
                path = Path(mount['source'])
                if not path.is_absolute() or not path.exists():
                    raise ValueError('A required native bind source is missing')
            elif mount['type'] == 'volume':
                volume = volumes[mount['source']]
                if volume.get('external') is not True:
                    raise ValueError('Persistent native volumes must be explicitly external')
                row = json.loads(capture(['docker', 'volume', 'inspect', volume['name']]))[0]
                if (row['Name'] != volume['name'] or row['Driver'] != 'local'
                        or row.get('CreatedAt') != identities['volumes'][mount['source']]):
                    raise ValueError('Accepted persistent native volume is unavailable')
            else:
                raise ValueError('Unsupported native mount type')
        for key in service.get('networks', {}):
            network = networks[key]
            row = json.loads(capture(['docker', 'network', 'inspect', network['name']]))[0]
            if (row['Driver'] != 'bridge' or row['Internal'] != network.get('internal', False)
                    or row['Id'] != identities['networks'][key]):
                raise ValueError('Accepted native network identity or isolation differs')


def validate_project(stack: str, services: set[str]) -> None:
    identities = capture(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project='+stack]).decode().split()
    if identities:
        rows = json.loads(capture(['docker', 'inspect', *identities]))
        if any(row['Config']['Labels'].get('com.docker.compose.service') not in services for row in rows):
            raise ValueError('An unadmitted container belongs to the native Compose project')


def write_recipe(stack: str, recipe: dict) -> Path:
    if STATE.resolve() != STATE or STATE.stat().st_uid != os.geteuid() or STATE.stat().st_mode & 0o077:
        raise ValueError('Compiled native recipes require a private owned state directory')
    descriptor, temporary = tempfile.mkstemp(prefix=stack+'-', suffix='.tmp', dir=STATE)
    try:
        with os.fdopen(descriptor, 'w') as output:
            json.dump(recipe, output)
            output.flush()
            os.fsync(output.fileno())
        path = STATE/(stack+'.json')
        os.replace(temporary, path)
        return path
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def recover_proxy_networks(recipe: dict, identities: dict) -> None:
    """Restore only SWAG's admitted bridge attachments after a partial boot start."""
    if set(recipe['services']) != {'swag'}:
        raise ValueError('Proxy recovery requires the single accepted SWAG service')
    service = recipe['services']['swag']
    networks = recipe.get('networks', {})
    if (service.get('container_name') != 'swag' or service.get('network_mode')
            or set(service.get('networks', {})) != {'proxynet', 'socket-proxy-net'}):
        raise ValueError('Proxy recovery requires the accepted two-network topology')
    row = json.loads(capture(['docker', 'inspect', 'swag']))[0]
    labels = row['Config'].get('Labels') or {}
    image = json.loads(capture(['docker', 'image', 'inspect', service['image']]))[0]
    expected = {networks[key]['name']: key for key in service['networks']}
    attached = row['NetworkSettings']['Networks']
    if (row['Name'] != '/swag' or row['Image'] != image['Id']
            or labels.get('com.docker.compose.project') != 'swag'
            or labels.get('com.docker.compose.service') != 'swag'
            or not set(attached) <= set(expected)
            or any(value['NetworkID'] != identities['networks'][expected[name]]
                   for name, value in attached.items())):
        raise ValueError('Existing proxy identity or network attachments differ')
    commands = []
    for name, key in expected.items():
        if name in attached:
            continue
        settings = service['networks'][key] or {}
        if set(settings) - {'aliases'}:
            raise ValueError('Proxy recovery cannot infer missing static network settings')
        aliases = sorted({'swag', *settings.get('aliases', [])})
        command = ['docker', 'network', 'connect']
        for alias in aliases:
            command += ['--alias', alias]
        commands.append(command + [name, row['Id']])
    # Validate the whole plan before attaching anything. Never disconnect a network.
    for command in commands:
        capture(command)


def compose_arguments(arguments: list[str], services: set[str], local_images: set[str]) -> list[str] | None:
    if not arguments or arguments[0] not in {'config', 'ps', 'pull', 'up', 'restart', 'start', 'stop', 'exec'}:
        raise ValueError('Unsupported native deployment Compose command')
    if arguments[0] == 'exec':
        position = 2 if arguments[1:2] == ['-T'] else 1
        if len(arguments) <= position+1 or arguments[position] not in services:
            raise ValueError('Native exec requires an accepted service and explicit command')
        return arguments
    if arguments[0] == 'pull':
        if any(value != '--ignore-buildable' for value in arguments[1:]):
            raise ValueError('Unsupported native pull arguments')
        selected = sorted(services-local_images)
        return arguments+selected if selected else None
    if arguments[0] in {'up', 'restart', 'start', 'stop'}:
        options = {'-d', '--detach', '--build', '--no-build', '--remove-orphans',
                   '--no-deps', '--wait', '--force-recreate', '--no-recreate'}
        targets = []
        position = 1
        while position < len(arguments):
            value = arguments[position]
            if value in {'--wait-timeout', '--timeout'}:
                position += 1
                if position >= len(arguments) or not arguments[position].isdigit() or int(arguments[position]) > 600:
                    raise ValueError('Invalid native Compose timeout')
            elif value in options:
                pass
            elif value in services:
                targets.append(value)
            else:
                raise ValueError('Unsupported native Compose option or unreleased service')
            position += 1
        return arguments if targets else arguments+sorted(services)
    return arguments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('/srv/Docker'))
    parser.add_argument('--policy', type=Path, default=POLICY)
    parser.add_argument('--recover-proxy-networks', action='store_true')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--admit', nargs='+')
    action.add_argument('--stack')
    parser.add_argument('compose_arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        policy = load_policy(args.policy)
        if args.repo.resolve() != args.repo or str(args.repo) != policy['repository']:
            raise ValueError('Native deployment checkout differs from accepted repository')
        if sys.platform != 'linux' or os.uname().nodename != policy['hostname']:
            raise ValueError('Native deployment host identity differs')
        check = Path(__file__).with_name('check_media_mount.py')
        capture([sys.executable, '-B', str(check), '--config', str(args.policy.parent/'media-mount-policy.json')])
        for stack in args.admit or [args.stack]:
            if stack not in policy['stacks']:
                raise ValueError('Native stack is not released: '+stack)
            recipe, local = compile_recipe(render_source(args.repo, stack), policy['stacks'][stack])
            validate_resources(recipe, local, policy['stacks'][stack]['resourceIdentities'])
            validate_project(stack, set(recipe['services']))
            if args.stack:
                arguments = args.compose_arguments
                if arguments[:1] == ['--']:
                    arguments = arguments[1:]
                command = compose_arguments(arguments, set(recipe['services']), local)
                if command is None:
                    return 0
                if args.recover_proxy_networks:
                    if stack != 'swag' or command != ['start', 'swag']:
                        raise ValueError('Proxy network recovery is restricted to start swag')
                    recover_proxy_networks(recipe, policy['stacks'][stack]['resourceIdentities'])
                path = write_recipe(stack, recipe)
                return subprocess.run(['docker', 'compose', '--profile', '*', '--project-name', stack,
                    '--project-directory', str(args.repo/stack), '-f', str(path), *command], check=False).returncode
        print('Native deployment storage, networks, images and mount admission passed')
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        print('Native deployment held; inspect the accepted host policy and source recipe', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
