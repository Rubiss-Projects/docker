"""Private PostgreSQL roles, credentials, ownership and ACL recovery proofs."""

from __future__ import annotations

import json
import re
import shlex
import subprocess

ROLE_SQL = """SELECT coalesce(json_agg(t ORDER BY rolname),'[]') FROM
(SELECT rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,
rolreplication,rolconnlimit,rolpassword,rolvaliduntil,rolbypassrls
FROM pg_authid WHERE rolname !~ '^pg_' AND rolname <> 'verifier') t;
SELECT coalesce(json_agg(t ORDER BY role,member,grantor),'[]') FROM
(SELECT pg_get_userbyid(roleid) AS role,pg_get_userbyid(member) AS member,
pg_get_userbyid(grantor) AS grantor,admin_option FROM pg_auth_members) t;
SELECT coalesce(json_agg(t ORDER BY role,database),'[]') FROM
(SELECT pg_get_userbyid(setrole) AS role,
CASE WHEN setdatabase=0 THEN '' ELSE (SELECT datname FROM pg_database WHERE oid=setdatabase) END AS database,
setconfig FROM pg_db_role_setting WHERE setrole<>0 OR setdatabase=(SELECT oid FROM pg_database WHERE datname=current_database())) t;
"""

# Use names instead of cluster-local OIDs, and normalize ACL ordering.
SECURITY_SQL = """WITH objects AS (
SELECT 'database' AS kind,current_database() AS name,datdba AS owner,datacl AS acl FROM pg_database WHERE datname=current_database()
UNION ALL SELECT 'schema',quote_ident(nspname),nspowner,nspacl FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname<>'information_schema'
UNION ALL SELECT 'relation',format('%I.%I',n.nspname,c.relname),c.relowner,c.relacl FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
UNION ALL SELECT 'column',format('%I.%I.%I',n.nspname,c.relname,a.attname),c.relowner,a.attacl FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND c.relkind IN ('r','p','v','m','f') AND a.attnum>0 AND NOT a.attisdropped
UNION ALL SELECT 'function',format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)),p.proowner,p.proacl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
UNION ALL SELECT 'type',format('%I.%I',n.nspname,t.typname),t.typowner,t.typacl FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
UNION ALL SELECT 'default',format('%s:%s:%s',pg_get_userbyid(d.defaclrole),coalesce(n.nspname,''),d.defaclobjtype),d.defaclrole,d.defaclacl FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace)
SELECT json_build_array(kind,name,pg_get_userbyid(owner),
CASE WHEN acl IS NULL THEN NULL ELSE (SELECT json_agg(v ORDER BY v::text) FROM
(SELECT json_build_array(pg_get_userbyid(grantor),CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,is_grantable) AS v FROM aclexplode(acl)) q) END)
FROM objects ORDER BY kind,name;
"""


def json_values(output: bytes) -> list:
    """psql may wrap aggregate JSON records across physical output lines."""
    decoder = json.JSONDecoder()
    remaining = output.decode().strip()
    result = []
    while remaining:
        value, end = decoder.raw_decode(remaining)
        result.append(value)
        remaining = remaining[end:].lstrip()
    return result


def roles_for_existing_bootstrap(dump: bytes, user: str) -> bytes:
    """Skip only initdb's existing CREATE, retaining its ALTER/password/grants."""
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', user):
        raise ValueError('Unsupported PostgreSQL bootstrap role')
    candidates = {f'CREATE ROLE {user};', f'CREATE ROLE "{user}";'}
    lines = dump.decode().splitlines(keepends=True)
    matching = [i for i, line in enumerate(lines) if line.rstrip('\r\n') in candidates]
    if len(matching) != 1:
        raise ValueError('PostgreSQL bootstrap CREATE statement is not unique')
    return ''.join(line for i, line in enumerate(lines) if i != matching[0]).encode()


def inventory(command, prefix: list[str]) -> dict:
    roles, memberships, settings = json_values(command(prefix, input=ROLE_SQL.encode()))
    objects = json_values(command(prefix, input=SECURITY_SQL.encode()))
    if not roles or not objects:
        raise ValueError('PostgreSQL security inventory is empty')
    return {'roles': roles, 'memberships': memberships, 'settings': settings, 'objects': objects}


def capture(command, job, app: dict, database: dict, user: str, name: str, prefix: list[str]) -> dict:
    source = inventory(command, prefix)
    # The dedicated source currently has no custom tablespaces or other databases.
    scope = json.loads(command(prefix, input=b"SELECT json_build_array((SELECT count(*) FROM pg_tablespace WHERE spcname NOT IN ('pg_default','pg_global')),(SELECT count(*) FROM pg_database WHERE NOT datistemplate AND datname NOT IN ('postgres',current_database())),(SELECT count(*) FROM pg_authid WHERE rolname='verifier'));"))
    if scope != [0, 0, 0]:
        raise ValueError('PostgreSQL bootstrap scope requires separate admission')
    app_env = dict(v.split('=', 1) for v in app['Config']['Env'])
    db_env = dict(v.split('=', 1) for v in database['Config']['Env'])
    password = app_env.get('BW_DB_PASSWORD')
    if not password or password != db_env.get('POSTGRES_PASSWORD'):
        raise ValueError('Current application and database credentials differ')
    roles = command(['docker', 'exec', database['Id'], 'pg_dumpall', '--roles-only',
                     '--no-password', '-U', user, '-l', name])
    credentials = json.dumps({'user': user, 'database': name, 'password': password}).encode()
    for filename, data in [('roles.private.sql', roles), ('credentials.private.json', credentials)]:
        if not 0 < len(data) <= 1024*1024:
            raise ValueError('PostgreSQL bootstrap material exceeds its bound')
        job.write(filename, data)
    return source


def verify_login(helper: str, credentials: dict) -> None:
    """Use the captured password through stdin, never command arguments or logs."""
    script = ('export PGPASSWORD='+shlex.quote(credentials['password'])+'\nexec psql -X -qAt '
              '--no-password -h 127.0.0.1 -U '+shlex.quote(credentials['user'])+
              ' -d '+shlex.quote(credentials['database'])+" -c 'SELECT 1;'\n")
    result = subprocess.run(['docker', 'exec', '-i', helper, 'sh', '-s'], input=script.encode(),
                            capture_output=True, timeout=30)
    if result.returncode or result.stdout.strip() != b'1':
        raise ValueError('Restored application credential authentication failed')
