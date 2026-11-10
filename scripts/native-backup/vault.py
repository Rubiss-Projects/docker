#!/usr/bin/env python3
"""Consistent Bitwarden Lite PostgreSQL and confined application-file recovery."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import stat
import subprocess
import time
import uuid

from confined_files import SafeTree
import portainer
import vault_security

APP = 'bitwarden'
DATABASE = 'bitwarden-db-1'
VOLUME = 'native-return-20261110-v005'
SOURCE = Path('/var/lib/docker/volumes')/VOLUME/'_data/config'
POSTGRES_IMAGE = 'sha256:0d27c7e73f040f9c443f06fb4c0d4d32c46832ea263c4fe5ae86ffe0a48c6fec'
MAX_DUMP_BYTES = 128*1024*1024
HELPER_LABEL = 'native-backup.scope=vault-restore'
TABLE_SQL = r"""SET TIME ZONE 'UTC';
SELECT format('SELECT json_build_array(%L, %L, count(*)::text, md5(coalesce(string_agg(d, '''' ORDER BY d), ''''))) FROM (SELECT md5(row_to_json(t)::text) AS d FROM %I.%I AS t) AS rows', schemaname, tablename, schemaname, tablename) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname,tablename
\gexec
"""


def command(arguments: list[str], *, input: bytes | None = None, timeout: int = 120,
            diagnostic: tuple[SafeTree, str] | None = None) -> bytes:
    result = subprocess.run(arguments, input=input, capture_output=True, timeout=timeout)
    if diagnostic is not None:
        tree, name = diagnostic
        tree.write(name, result.stderr)
    if result.returncode:
        # Docker/SQL errors may contain application data or connection settings.
        raise RuntimeError('Vault backup subprocess failed; inspect private job state')
    return result.stdout


def table_inventory(output: bytes) -> dict:
    result = {}
    for line in output.decode().splitlines():
        schema, name, count, digest = json.loads(line)
        if not isinstance(schema, str) or not isinstance(name, str):
            raise ValueError('Invalid PostgreSQL table identity')
        if not re.fullmatch(r'[0-9]+', count) or not re.fullmatch(r'[0-9a-f]{32}', digest):
            raise ValueError('Invalid PostgreSQL table proof')
        key = json.dumps([schema, name], separators=(',', ':'))
        if key in result:
            raise ValueError('Duplicate PostgreSQL table proof')
        result[key] = {'rows': int(count), 'contentMd5': digest}
    if not result:
        raise ValueError('PostgreSQL capture has no application tables')
    return result


def require_vault_tables(tables: dict) -> None:
    required = {json.dumps(['public', name], separators=(',', ':')) for name in ['User', 'Cipher']}
    if not required.issubset(tables):
        raise ValueError('Required Bitwarden application tables are missing')


def check_no_retained_helpers() -> None:
    if command(['docker', 'ps', '-aq', '--filter', 'label='+HELPER_LABEL]).strip():
        raise RuntimeError('Reconcile a retained vault restore helper before another job')


def file_inventory(tree: SafeTree) -> dict:
    """Only the application's root log directory is non-restorative."""
    entries = {}
    with tree.fd('.', os.O_RDONLY | os.O_DIRECTORY) as root:
        names = sorted(os.listdir(root))
    selected = []
    for name in names:
        if name == 'logs' and stat.S_ISDIR(tree.lstat(name).st_mode):
            continue
        selected.extend(tree.walk(name))
    for relative in selected:
        value = tree.lstat(relative)
        row = tree.metadata(relative)
        if stat.S_ISDIR(value.st_mode):
            row['kind'] = 'directory'
        elif stat.S_ISREG(value.st_mode):
            row.update(kind='file', bytes=value.st_size, sha256=tree.digest(relative))
        else:
            raise ValueError('Vault application files must not contain links or special files')
        entries[relative] = row
    for key in ['identity.pfx', 'Web/app-id.json']:
        if entries.get(key, {}).get('kind') != 'file' or not entries[key]['bytes']:
            raise ValueError('Vault identity material is missing')
    if not any(name.startswith('data-protection/key-') and name.endswith('.xml')
               and row['kind'] == 'file' and row['bytes'] for name, row in entries.items()):
        raise ValueError('Vault data-protection keys are missing')
    return entries


def admit() -> tuple[dict, dict, str, str]:
    app, database = [portainer.container_state(name) for name in [APP, DATABASE]]
    if database['Image'] != POSTGRES_IMAGE:
        raise ValueError('PostgreSQL image requires a separately admitted backup producer')
    mounts = app['HostConfig'].get('Mounts') or []
    if not any(m.get('Type') == 'volume' and m.get('Source') == VOLUME
               and m.get('Target') == '/etc/bitwarden'
               and m.get('VolumeOptions', {}).get('Subpath') == 'config' for m in mounts):
        raise ValueError('Unexpected Bitwarden application mount')
    volume = json.loads(command(['docker', 'volume', 'inspect', VOLUME]))[0]
    if volume['Driver'] != 'local' or volume.get('Options') or Path(volume['Mountpoint'])/'config' != SOURCE:
        raise ValueError('Unexpected Bitwarden volume backend')
    env = dict(value.split('=', 1) for value in database['Config']['Env'])
    user = env.get('POSTGRES_USER', 'postgres')
    name = env.get('POSTGRES_DB', user)
    if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value) for value in [user, name]):
        raise ValueError('Unsupported PostgreSQL account or database name')
    settings = dict(value.split('=', 1) for value in app['Config']['Env'])
    expected = {'BW_DB_PROVIDER': 'postgresql', 'BW_DB_SERVER': 'db',
                'BW_DB_DATABASE': name, 'BW_DB_USERNAME': user}
    if any(settings.get(key) != value for key, value in expected.items()):
        raise ValueError('Bitwarden is not using the admitted PostgreSQL backend')
    if not any('db' in (network.get('Aliases') or [])
               for network in database['NetworkSettings']['Networks'].values()):
        raise ValueError('PostgreSQL service alias is missing')
    return app, database, user, name


def snapshot_database(job: SafeTree, user: str, database: str) -> dict:
    """Keep the exporting transaction alive until dump and content proof finish."""
    options = '-c statement_timeout=120000 -c idle_in_transaction_session_timeout=600000'
    prefix = ['docker', 'exec', '-e', 'PGOPTIONS='+options, '-i', DATABASE,
              'psql', '-X', '-qAt', '--no-password', '-v', 'ON_ERROR_STOP=1',
              '-U', user, '-d', database]
    with job.fd('snapshot.private.stderr', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as error:
        snapshot = subprocess.Popen(prefix, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error)
        try:
            snapshot.stdin.write(b'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n')
            snapshot.stdin.flush()
            with selectors.DefaultSelector() as ready:
                ready.register(snapshot.stdout, selectors.EVENT_READ)
                if not ready.select(15):
                    raise TimeoutError('PostgreSQL snapshot admission timed out')
            identifier = snapshot.stdout.readline().decode().strip()
            if not re.fullmatch(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9]+', identifier):
                raise ValueError('Unexpected exported PostgreSQL snapshot identifier')
            with job.fd('database.pgdump', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as output:
                def limit_dump() -> None:
                    import resource
                    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_DUMP_BYTES, MAX_DUMP_BYTES))
                result = subprocess.run(['docker', 'exec', '-e', 'PGOPTIONS='+options, DATABASE,
                    'pg_dump', '--no-password', '-U', user, '-d', database, '--format=custom',
                    '--snapshot='+identifier], stdout=output, stderr=subprocess.PIPE,
                    timeout=150, preexec_fn=limit_dump)
                os.fsync(output)
            job.write('pg-dump.private.stderr', result.stderr)
            if result.returncode:
                raise RuntimeError('PostgreSQL snapshot dump failed')
            sql = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSET TRANSACTION SNAPSHOT '"+identifier+"';\n"+TABLE_SQL+'COMMIT;\n'
            tables = table_inventory(command(prefix, input=sql.encode(), timeout=150,
                diagnostic=(job, 'table-inventory.private.stderr')))
            require_vault_tables(tables)
            snapshot.stdin.write(b'COMMIT;\n\\q\n')
            snapshot.stdin.flush()
            snapshot.stdin.close()
            if snapshot.wait(timeout=15):
                raise RuntimeError('PostgreSQL exporting transaction did not close successfully')
        finally:
            if snapshot.poll() is None:
                # Closing the read-only session rolls back its transaction. An
                # uncertain client remains recorded by the outer capture intent.
                snapshot.kill()
                snapshot.wait(timeout=15)
            for stream in [snapshot.stdin, snapshot.stdout]:
                if stream is not None and not stream.closed:
                    stream.close()
    size = job.lstat('database.pgdump').st_size
    if not 0 < size <= MAX_DUMP_BYTES:
        raise ValueError('PostgreSQL dump exceeds the admitted size')
    return {'bytes': size, 'sha256': job.digest('database.pgdump'), 'tables': tables,
            'sameExportedSnapshotForDumpAndTableInventory': True}


def inspect_capture(destination: Path) -> dict:
    with SafeTree(destination) as job:
        proof = json.loads(job.read('capture.json'))
        job.require_regular('database.pgdump')
        dump = proof['database']
        require_vault_tables(dump['tables'])
        if not 0 < job.lstat('database.pgdump').st_size == dump['bytes'] <= MAX_DUMP_BYTES:
            raise ValueError('PostgreSQL dump size differs')
        if job.digest('database.pgdump') != dump['sha256']:
            raise ValueError('PostgreSQL dump digest differs')
        for name, row in proof['bootstrapFiles'].items():
            job.require_regular(name)
            if job.lstat(name).st_size != row['bytes'] or job.digest(name) != row['sha256']:
                raise ValueError('PostgreSQL role or credential material differs')
        if set(proof['bootstrapFiles']) != {'roles.private.sql', 'credentials.private.json'}:
            raise ValueError('PostgreSQL bootstrap material is incomplete')
    with SafeTree(destination/'application-files') as payload:
        if file_inventory(payload) != proof['applicationFiles']:
            raise ValueError('Vault restored keys, attachments or metadata differ')
    return proof


def capture(destination: Path) -> dict:
    if os.geteuid() != 0:
        raise RuntimeError('Vault capture requires the root backup service')
    os.umask(0o077)
    check_no_retained_helpers()
    app, database, user, name = admit()
    with SafeTree(destination.parent) as parent:
        parent.mkdir(destination.name)
    with SafeTree(destination) as job, SafeTree(SOURCE) as source:
        job.write('intent.json', json.dumps({'at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'applicationId': app['Id'], 'databaseId': database['Id'], 'applicationControls': 0}).encode())
        before = file_inventory(source)
        prefix = ['docker', 'exec', '-i', DATABASE, 'psql', '-X', '-qAt', '--no-password',
                  '-v', 'ON_ERROR_STOP=1', '-U', user, '-d', name]
        security = vault_security.capture(command, job, app, database, user, name, prefix)
        dump = snapshot_database(job, user, name)
        if vault_security.inventory(command, prefix) != security:
            raise ValueError('PostgreSQL roles or privileges changed during capture')
        if file_inventory(source) != before:
            raise ValueError('Vault files changed across the database checkpoint')
        job.mkdir('application-files')
        with SafeTree(destination/'application-files') as payload:
            for relative, row in before.items():
                if row['kind'] == 'directory':
                    payload.mkdir(relative)
                else:
                    copied = payload.copy_from(source, relative)
                    if copied != {k: row[k] for k in ['uid', 'gid', 'mode', 'mtimeNs', 'xattrs']} or payload.digest(relative) != row['sha256']:
                        raise ValueError('Vault file changed during confined capture')
            for relative, row in sorted(before.items(), key=lambda item: item[0].count('/'), reverse=True):
                payload.apply_metadata(relative, row)
        if file_inventory(source) != before:
            raise ValueError('Vault files changed during recovery-set capture')
        if [portainer.identity(value) for value in [app, database]] != [
                portainer.identity(portainer.container_state(value)) for value in [APP, DATABASE]]:
            raise ValueError('Vault source container changed during capture')
        proof = {'at': dt.datetime.now(dt.timezone.utc).isoformat(),
                 'method': 'postgres_exported_snapshot_with_stable_vault_files',
                 'applicationImageId': app['Image'], 'postgresImageId': database['Image'],
                 'postgresVersion': command(['docker', 'exec', DATABASE, 'postgres', '--version']).decode().strip(),
                 'postgresBinarySha256': command(['docker', 'exec', DATABASE, 'sha256sum', '/usr/lib/postgresql/14/bin/postgres']).decode().split()[0],
                 'database': dump, 'applicationFiles': before, 'applicationControls': 0,
                 'securityInventory': security,
                 'bootstrapFiles': {name: {'bytes': job.lstat(name).st_size,
                     'sha256': job.digest(name)} for name in ['roles.private.sql', 'credentials.private.json']},
                 'sourceContainerIdentitiesUnchanged': True,
                 'databaseRoleCredentialsOwnershipAclIncluded': True,
                 'encryptedRepositoryCapturePending': True}
        job.write('capture.json', json.dumps(proof, indent=2).encode())
    inspect_capture(destination)
    return proof


def verify_database(destination: Path) -> None:
    """Restore once in an isolated PostgreSQL helper; retain uncertain helpers."""
    proof = inspect_capture(destination)
    if proof['postgresImageId'] != POSTGRES_IMAGE:
        raise ValueError('Unexpected PostgreSQL restore image')
    check_no_retained_helpers()
    helper = 'native-backup-vault-'+uuid.uuid4().hex
    with SafeTree(destination) as job:
        credentials = json.loads(job.read('credentials.private.json'))
        bootstrap_user = credentials['user']
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', bootstrap_user):
            raise ValueError('Unsupported PostgreSQL bootstrap role')
        job.write('restore-helper-intent.json', json.dumps({'helperName': helper,
            'label': HELPER_LABEL, 'network': 'none', 'applicationIdentityStarted': False}).encode())
    # initdb's role also owns built-in grants and the initial public schema.
    startup = 'initdb -D /verify/pgdata -U '+shlex.quote(bootstrap_user)+' --auth-local=trust --auth-host=scram-sha-256 >/verify/init.log 2>&1; exec postgres -D /verify/pgdata -k /verify -c listen_addresses=127.0.0.1 -c unix_socket_permissions=0700'
    identifier = command(['docker', 'run', '--detach', '--pull=never', '--name', helper,
        '--label', HELPER_LABEL, '--network', 'none', '--read-only', '--restart', 'no',
        '--user', '999:999', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--memory', '768m', '--memory-swap', '768m', '--cpus', '1', '--pids-limit', '128',
        '--stop-signal', 'SIGINT', '--stop-timeout', '30',
        '--tmpfs', '/verify:rw,nosuid,nodev,noexec,size=512m,uid=999,gid=999,mode=0700',
        '--tmpfs', '/var/lib/postgresql/data:ro,nosuid,nodev,noexec,size=1m,uid=999,gid=999,mode=0700',
        '--entrypoint', '/bin/sh', POSTGRES_IMAGE, '-ec', startup], timeout=30).decode().strip()
    if not re.fullmatch('[0-9a-f]{64}', identifier):
        raise ValueError('Unexpected PostgreSQL restore helper identity')
    deadline = time.monotonic()+60
    while True:
        state = json.loads(command(['docker', 'inspect', helper]))[0]
        if state['Id'] != identifier or state['Image'] != POSTGRES_IMAGE or not state['State']['Running']:
            raise RuntimeError('Retain the isolated PostgreSQL helper for reconciliation')
        host = state['HostConfig']
        if (host['NetworkMode'] != 'none' or host.get('PortBindings')
                or not host['ReadonlyRootfs'] or host['CapDrop'] != ['ALL']
                or state['Config']['User'] != '999:999'
                or host['Memory'] != 768*1024*1024 or host['PidsLimit'] != 128
                or set(host.get('Tmpfs') or {}) != {'/verify', '/var/lib/postgresql/data'}
                or not any(s.split(':')[0] == 'no-new-privileges' for s in host['SecurityOpt'])
                or any(m['Type'] != 'tmpfs' for m in state['Mounts'])):
            raise ValueError('Isolated PostgreSQL helper confinement differs')
        ready = subprocess.run(['docker', 'exec', helper, 'pg_isready', '-h', '/verify', '-U', bootstrap_user], capture_output=True, timeout=10)
        if ready.returncode == 0:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('Observe the existing PostgreSQL restore helper')
        time.sleep(.5)
    if command(['docker', 'exec', helper, 'postgres', '--version']).decode().strip() != proof['postgresVersion']:
        raise ValueError('PostgreSQL restore version differs')
    if command(['docker', 'exec', helper, 'sha256sum', '/usr/lib/postgresql/14/bin/postgres']).decode().split()[0] != proof['postgresBinarySha256']:
        raise ValueError('PostgreSQL restore binary differs')
    with SafeTree(destination) as job:
        roles = vault_security.roles_for_existing_bootstrap(job.read('roles.private.sql'), bootstrap_user)
        command(['docker', 'exec', '-i', helper, 'psql', '-X', '-q', '-v',
            'ON_ERROR_STOP=1', '-h', '/verify', '-U', bootstrap_user, '-d', 'postgres'],
            input=roles, diagnostic=(job, 'roles-restore.private.stderr'))
        command(['docker', 'exec', '-i', helper, 'pg_restore', '--exit-on-error',
            '--create', '-h', '/verify',
            '-U', bootstrap_user, '-d', 'postgres'], input=job.read('database.pgdump'), timeout=150,
            diagnostic=(job, 'pg-restore.private.stderr'))
        restored = table_inventory(command(['docker', 'exec', '-i', helper, 'psql', '-X',
            '-qAt', '-v', 'ON_ERROR_STOP=1', '-h', '/verify', '-U', bootstrap_user, '-d', credentials['database']],
            input=TABLE_SQL.encode(), timeout=150, diagnostic=(job, 'restored-tables.private.stderr')))
        prefix = ['docker', 'exec', '-i', helper, 'psql', '-X', '-qAt', '-v',
                  'ON_ERROR_STOP=1', '-h', '/verify', '-U', bootstrap_user, '-d', credentials['database']]
        if vault_security.inventory(command, prefix) != proof['securityInventory']:
            raise ValueError('Restored PostgreSQL roles, ownership or privileges differ')
        auth = command(prefix, input=b"SELECT count(*) FROM pg_hba_file_rules WHERE type='host' AND auth_method<>'scram-sha-256';")
        if auth.strip() != b'0':
            raise ValueError('Restored PostgreSQL TCP authentication is not password verified')
        vault_security.verify_login(helper, credentials)
    if restored != proof['database']['tables']:
        raise ValueError('Restored PostgreSQL table contents differ')
    state = json.loads(command(['docker', 'inspect', helper]))[0]
    host = state['HostConfig']
    if (state['Id'] != identifier or host['NetworkMode'] != 'none' or host.get('PortBindings')
            or not host['ReadonlyRootfs'] or host['CapDrop'] != ['ALL']
            or set(host.get('Tmpfs') or {}) != {'/verify', '/var/lib/postgresql/data'}
            or any(m['Type'] != 'tmpfs' for m in state['Mounts'])):
        raise ValueError('Isolated PostgreSQL helper confinement differs')
    command(['docker', 'stop', '--time', '30', identifier], timeout=45)
    state = json.loads(command(['docker', 'inspect', helper]))[0]
    if state['Id'] != identifier or state['State']['Running'] or state['State']['ExitCode'] != 0 or state['State']['OOMKilled']:
        raise RuntimeError('Retain the stopped PostgreSQL helper for reconciliation')
    command(['docker', 'rm', identifier])
    with SafeTree(destination) as job:
        job.write('database-restore-verification.json', json.dumps({'tablesVerified': len(restored),
            'rowsVerified': sum(row['rows'] for row in restored.values()),
            'matchingPostgresBinary': True, 'network': 'none', 'dataOnlyInPrivateTmpfs': True,
            'rolesPasswordsMembershipsSettingsOwnershipAndAclMatched': True,
            'capturedApplicationPasswordAuthenticatedOverTcp': True,
            'bitwardenApplicationIdentityStarted': False, 'helperRemovedAfterCleanExit': True}).encode())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['capture', 'verify'])
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run through the root-owned native backup service')
    proof = capture(args.destination) if args.operation == 'capture' else inspect_capture(args.destination)
    if args.operation == 'verify':
        verify_database(args.destination)
    print(json.dumps({'method': proof['method'], 'tables': len(proof['database']['tables']),
                      'files': sum(r['kind'] == 'file' for r in proof['applicationFiles'].values()),
                      'applicationControls': 0}))
