#!/usr/bin/env python3
"""Render the n8n candidate without reading service secrets or starting a server."""
import json, os, subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parent.parent
def render(candidate):
    args=['docker','compose','--env-file',os.devnull,'--project-directory',str(REPO/'n8n'),'-f',str(REPO/'n8n/docker-compose.yml')]
    if candidate:args+=['-f',str(HERE/'overrides/n8n.yaml')]
    return json.loads(subprocess.check_output([*args,'config','--no-env-resolution','--no-interpolate','--no-path-resolution','--format','json'],text=True,stderr=subprocess.PIPE))
base,native=render(False),render(True)
a,b=base['services']['n8n'],native['services']['n8n']
assert {k:v for k,v in a.items() if k not in ('entrypoint','command','volumes')}=={k:v for k,v in b.items() if k not in ('entrypoint','command','volumes')}
assert b['entrypoint']==['tini','--','/bin/sh','/opt/nas-migration/n8n-native-start.sh'] and not b.get('command')
mounts={m['target']:m for m in b['volumes']}
assert set(mounts)=={'/root/.n8n','/files','/srv/Docker','/opt/nas-migration/n8n-startup-admission.cjs','/opt/nas-migration/n8n-native-start.sh','/opt/nas-migration/n8n-startup-policy.json'}
assert all(m['type']=='bind' and m['bind']['create_host_path'] is False for m in mounts.values())
assert all(m.get('read_only',False) for target,m in mounts.items() if target!='/root/.n8n')
assert mounts['/root/.n8n']['source']=='./config' and not mounts['/root/.n8n'].get('read_only',False)
assert not any('/mnt/e' in m['target'] for m in mounts.values())
assert '/files/import-workflows.sh' not in json.dumps(b)
print(json.dumps({'n8nCandidateRenderPassed':True,'legacyImporterBypassed':True,'legacyWritableAppBindsRemoved':True,'repoAndCodeReadonly':True,'hostPathAutoCreationDisabled':True,'imagesEnvironmentPortsAndLimitsUnchanged':True,'schedulerStarted':False,'engineActions':0,'nativeRuntimeAccepted':False}))
