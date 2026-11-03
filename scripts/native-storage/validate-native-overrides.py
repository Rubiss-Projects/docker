#!/usr/bin/env python3
"""Render native candidates without interpolation, env-file resolution or starts."""

import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parent
REMOVED={'plex':{'/usr/lib/wsl/drivers','/usr/lib/wsl/lib'},'channels-dvr':{'/usr/lib/wsl/drivers','/usr/lib/wsl/lib'},'nvidia-smi-rest':{'/usr/lib/wsl/drivers','/usr/lib/wsl/lib'},'homepage':{'/c','/e'}}


def render(stack: str, override: bool) -> dict:
    base=REPO/stack/'docker-compose.yml'
    command=['docker','compose','--env-file','/dev/null','--project-directory',str(base.parent),'-f',str(base)]
    if override:command+=['-f',str(HERE/'overrides'/(stack+'.yaml'))]
    command+=['config','--no-env-resolution','--no-interpolate','--no-path-resolution','--format','json']
    return json.loads(subprocess.check_output(command,text=True,stderr=subprocess.PIPE))


def without_volumes(service: dict) -> dict:
    return {k:v for k,v in service.items() if k!='volumes'}


def normalized_mount(mount: dict) -> dict:
    m=dict(mount)
    if m.get('type')=='bind':m['bind']={k:v for k,v in m.get('bind',{}).items() if k!='create_host_path'}
    return m


def main() -> None:
    rows=[]
    for stack,removed in REMOVED.items():
        base,candidate=render(stack,False),render(stack,True)
        assert set(base['services'])==set(candidate['services'])
        assert {k:v for k,v in base.items() if k!='services'}=={k:v for k,v in candidate.items() if k!='services'}
        original=base['services'][stack];native=candidate['services'][stack]
        assert without_volumes(original)==without_volumes(native),stack+' changed a non-volume field'
        before=original.get('volumes',[]);after=native.get('volumes',[])
        assert {m['target'] for m in before}-{m['target'] for m in after}==removed
        assert [normalized_mount(m) for m in before if m['target'] not in removed]==[normalized_mount(m) for m in after]
        assert all(m.get('bind',{}).get('create_host_path') is False for m in after if m['type']=='bind')
        assert not any('/usr/lib/wsl' in m.get('source','') or m.get('source') in ('/mnt/c','/mnt/e') for m in after)
        rows.append({'stack':stack,'removedTargets':sorted(removed),'retainedMountCount':len(after),'imagesEnvironmentPortsLimitsAndGpuReservationsUnchanged':True,'hostPathAutoCreationDisabled':True})
    print(json.dumps({'renderValidationPassed':True,'stacks':rows,'runtimeAccepted':False,'engineActions':0,'secretsExpanded':False}))


if __name__=='__main__':main()
