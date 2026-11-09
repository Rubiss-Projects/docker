#!/usr/bin/env python3
"""Render native candidates without interpolation, env-file resolution or starts."""

import json
import os
from pathlib import Path
import subprocess
import yaml

HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parent
REMOVED={'plex':{'/usr/lib/wsl/drivers','/usr/lib/wsl/lib'},'channels-dvr':{'/usr/lib/wsl/drivers','/usr/lib/wsl/lib'},'nvidia-smi-rest':{'/usr/lib/wsl/drivers','/usr/lib/wsl/lib'},'homepage':{'/c','/e'}}
HOMEPAGE_ADDED={'/media','/app/config/widgets.yaml'}


def render(stack: str, override: bool) -> dict:
    base=REPO/stack/'docker-compose.yml'
    command=['docker','compose','--env-file',os.devnull,'--project-directory',str(base.parent),'-f',str(base)]
    if override:command+=['-f',str(HERE/'overrides'/(stack+'.yaml'))]
    command+=['config','--no-env-resolution','--no-interpolate','--no-path-resolution','--format','json']
    return json.loads(subprocess.check_output(command,text=True,stderr=subprocess.PIPE))


def without_volumes(service: dict) -> dict:
    return {k:v for k,v in service.items() if k!='volumes'}


def normalized_mount(mount: dict) -> dict:
    m=dict(mount)
    if m.get('type')=='bind':m['bind']={k:v for k,v in m.get('bind',{}).items() if k!='create_host_path'}
    return m


def validate_homepage_widgets(mounts: list[dict]) -> None:
    by_target={mount['target']:mount for mount in mounts}
    media=by_target['/media'];widgets=by_target['/app/config/widgets.yaml']
    assert media['source']=='/srv/Media' and media['read_only']
    assert widgets['source']=='../scripts/native-storage/homepage-widgets.native.yaml' and widgets['read_only']
    token='{{HOMEPAGE_VAR_OPENWEATHERMAP_API_KEY}}'
    def parse(path: Path) -> list[dict]:
        # Parse only this literal public placeholder; never resolve an environment.
        source=path.read_text()
        assert source.count(token)==1
        return yaml.safe_load(source.replace(token,'"PUBLIC_TOKEN_NOT_RESOLVED"'))
    before=parse(REPO/'homepage/config/widgets.yaml')
    after=parse(HERE/'homepage-widgets.native.yaml')
    assert len(before)==len(after)==3 and before[:2]==after[:2]
    assert {k:v for k,v in before[2]['resources'].items() if k!='disk'}=={k:v for k,v in after[2]['resources'].items() if k!='disk'}
    assert after[2]['resources']['disk']==['/app/config','/media']
    assert all(path in by_target for path in after[2]['resources']['disk'])


def main() -> None:
    rows=[]
    for stack,removed in REMOVED.items():
        base,candidate=render(stack,False),render(stack,True)
        assert set(base['services'])==set(candidate['services'])
        assert {k:v for k,v in base.items() if k!='services'}=={k:v for k,v in candidate.items() if k!='services'}
        original=base['services'][stack];native=candidate['services'][stack]
        assert without_volumes(original)==without_volumes(native),stack+' changed a non-volume field'
        before=original.get('volumes',[]);after=native.get('volumes',[])
        added=HOMEPAGE_ADDED if stack=='homepage' else set()
        assert {m['target'] for m in before}-{m['target'] for m in after}==removed
        assert {m['target'] for m in after}-{m['target'] for m in before}==added
        assert [normalized_mount(m) for m in before if m['target'] not in removed]==[normalized_mount(m) for m in after if m['target'] not in added]
        assert all(m.get('bind',{}).get('create_host_path') is False for m in after if m['type']=='bind')
        assert not any('/usr/lib/wsl' in m.get('source','') or m.get('source') in ('/mnt/c','/mnt/e') for m in after)
        if stack=='homepage':validate_homepage_widgets(after)
        rows.append({'stack':stack,'removedTargets':sorted(removed),'retainedMountCount':len(after),'imagesEnvironmentPortsLimitsAndGpuReservationsUnchanged':True,'hostPathAutoCreationDisabled':True})
    base,candidate=render('influxdb',False),render('influxdb',True)
    assert set(base['services'])==set(candidate['services'])
    assert {k:v for k,v in base.items() if k!='services'}=={k:v for k,v in candidate.items() if k!='services'}
    original=base['services']['influxdb'];native=candidate['services']['influxdb']
    assert native['stop_signal']=='SIGINT' and native['stop_grace_period'] in ('2m','2m0s')
    shutdown_fields={'stop_signal','stop_grace_period'}
    assert {k:v for k,v in original.items() if k not in shutdown_fields}=={k:v for k,v in native.items() if k not in shutdown_fields}
    rows.append({'stack':'influxdb','stopSignal':'SIGINT','stopGracePeriodSeconds':120,'allOtherServiceSettingsUnchanged':True})
    print(json.dumps({'renderValidationPassed':True,'stacks':rows,'runtimeAccepted':False,'engineActions':0,'secretsExpanded':False}))


if __name__=='__main__':main()
