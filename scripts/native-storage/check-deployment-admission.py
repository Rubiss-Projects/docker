#!/usr/bin/env python3
"""Read-only native deployment admission; never starts services or installs jobs."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

REQUIRED_OVERRIDES = frozenset({'plex', 'channels-dvr', 'nvidia-smi-rest', 'homepage', 'n8n', 'influxdb'})


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def load_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def plan_digest(plan):
    canonical = json.dumps(plan, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_private_policy(path):
    # Keep policy outside the writable checkout and reject redirectable/unsafe files.
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022:
        raise ValueError('Private policy directory must be root-owned and not writable by others')
    if not hasattr(os, 'O_NOFOLLOW'):
        raise ValueError('Native policy admission requires Linux no-follow file access')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Private policy must be a root-owned regular file, not writable by others')
        raw = os.read(fd, 65537)
        if len(raw) > 65536:
            raise ValueError('Private policy exceeds its size limit')
        return load_json(raw)
    finally:
        os.close(fd)


def reviewed_stacks(plan):
    if type(plan['schemaVersion']) is not int or plan['schemaVersion'] != 1 or plan['state'] != 'preparation_only' or plan['automaticStartAllowed'] is not False:
        raise ValueError('Expected the reviewed preparation plan; it is not startup authorization')
    rows = {}
    for row in plan['stacks']:
        name = row['stack']
        if not isinstance(name, str) or re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name) is None or name in rows:
            raise ValueError('Unknown or duplicate stack identity')
        compose = PurePosixPath(row['compose'])
        if compose.parent.as_posix() != name or compose.name not in ('docker-compose.yml', 'compose.yml', 'compose.yaml'):
            raise ValueError('Compose path does not match its reviewed stack')
        services = row['services']
        if not services or any(not isinstance(s, str) or not s for s in services) or len(set(services)) != len(services):
            raise ValueError('Expected explicit unique Compose service identities')
        rows[name] = row
    return rows


def validate_release(plan, policy):
    rows = reviewed_stacks(plan)
    expected = {'schemaVersion', 'nativeAcceptanceCompleted', 'startupPlanSha256', 'releasedStacks', 'allowedMaintenanceInstallers'}
    if set(policy) != expected or type(policy['schemaVersion']) is not int or policy['schemaVersion'] != 1 or policy['nativeAcceptanceCompleted'] is not True:
        raise ValueError('Native acceptance and private deployment release are not recorded')
    if policy['startupPlanSha256'] != plan_digest(plan):
        raise ValueError('The private release does not match the reviewed startup plan')
    released = policy['releasedStacks']
    if not isinstance(released, list) or any(not isinstance(x, str) for x in released) or len(set(released)) != len(released):
        raise ValueError('Expected an explicit unique released-stack list')
    if any(name not in rows or rows[name]['disposition'] != 'keep' for name in released):
        raise ValueError('A released stack is unknown, deferred, archived or awaiting replacement')
    installers = policy['allowedMaintenanceInstallers']
    if not isinstance(installers, dict):
        raise ValueError('Expected an explicit installer path-to-digest map')
    for name, digest in installers.items():
        if not isinstance(name, str) or not name.startswith('scripts/') or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
            raise ValueError('Invalid maintenance installer path')
        if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
            raise ValueError('Every released installer needs its reviewed SHA-256')
    return rows


def compose_files(repo, row):
    base = repo / row['compose']
    overlay = repo / 'scripts/native-storage/overrides' / (row['stack'] + '.yaml')
    files = [base]
    if row['stack'] in REQUIRED_OVERRIDES:
        files.append(overlay)
    elif overlay.exists():
        raise ValueError('Native overlay is outside the reviewed recipe mapping')
    if any(not p.is_file() or not p.resolve().is_relative_to(repo.resolve()) for p in files):
        raise ValueError('A native Compose input is absent or leaves the checkout')
    return files


def require_stack(rows, policy, name):
    if name not in rows or name not in policy['releasedStacks']:
        raise ValueError('Native stack has not been individually released: ' + name)
    return rows[name]


def check_services(repo, row):
    command = ['docker', 'compose']
    directory = repo / row['stack']
    for name in ('.env', '.env.secret'):
        if (directory / name).is_file():
            command.extend(['--env-file', name])
    for file in compose_files(repo, row):
        command.extend(['--file', str(file)])
    command.extend(['config', '--services'])
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)
    # Never print renderer diagnostics: they can contain expanded environment values.
    if result.returncode or sorted(result.stdout.splitlines()) != sorted(row['services']):
        raise ValueError('Native Compose services differ from the reviewed plan: ' + row['stack'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--policy', type=Path, default=Path('/etc/nas-migration/native-deployment-policy.json'))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--plan-digest', action='store_true')
    action.add_argument('--stacks', nargs='+')
    action.add_argument('--compose-stack')
    action.add_argument('--installer')
    args = parser.parse_args()
    try:
        repo = args.repo.resolve()
        if any(character in str(repo) for character in ('\r', '\n')):
            raise ValueError('Checkout path cannot contain a line break')
        plan = load_json((repo / 'scripts/native-storage/startup-plan.json').read_bytes())
        reviewed_stacks(plan)
        if args.plan_digest:
            print(plan_digest(plan))
            return 0
        policy = load_private_policy(args.policy)
        rows = validate_release(plan, policy)
        if args.compose_stack:
            row = require_stack(rows, policy, args.compose_stack)
            for file in compose_files(repo, row):
                print(file)
        elif args.installer:
            expected = policy['allowedMaintenanceInstallers'].get(args.installer)
            file = repo / args.installer
            if not expected or not file.is_file() or not file.resolve().is_relative_to(repo):
                raise ValueError('Maintenance installer has not been released')
            if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
                raise ValueError('Maintenance installer changed since its review')
            print('Reviewed native maintenance installer admitted; nothing executed')
        else:
            # Admit the entire changed/dependency/dependent plan before any mutation.
            selected = [require_stack(rows, policy, name) for name in args.stacks]
            for row in selected:
                check_services(repo, row)
            print('Native deployment plan and compiled service identities admitted')
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('Native deployment held: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
