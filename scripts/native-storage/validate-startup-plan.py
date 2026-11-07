#!/usr/bin/env python3
"""Validate preparation coverage; this tool cannot start services."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

import yaml


def validate(plan: dict, compositions: dict[str, list[str]]) -> None:
    if plan['schemaVersion'] != 1 or plan['state'] != 'preparation_only' or plan['automaticStartAllowed'] is not False:
        raise ValueError('This is a preparation-only plan, never startup authorization')
    rows=plan['stacks']; paths=[r['compose'] for r in rows]; stacks=[r['stack'] for r in rows]
    if len(set(paths))!=len(paths) or len(set(stacks))!=len(stacks):
        raise ValueError('Duplicate stack or Compose path')
    excluded=plan['excludedComposePaths']
    if len(set(excluded))!=len(excluded) or any(not p.startswith('pi/') for p in excluded):
        raise ValueError('Only explicitly listed Pi definitions are out of scope')
    if set(paths)&set(excluded) or set(paths)|set(excluded)!=set(compositions):
        raise ValueError('Every tracked Compose definition needs an explicit disposition')
    known=set(stacks)
    for row in rows:
        if row['disposition'] not in ('keep','replace','omit','defer','archive') or not row['releaseGates']:
            raise ValueError('Each stack needs a valid disposition and release gates')
        if row['services']!=compositions[row['compose']]:
            raise ValueError('Unreviewed Compose service change: '+row['stack'])
        if not set(row['after'])<=known or row['stack'] in row['after']:
            raise ValueError('Unknown or self startup dependency')
    visited=set(); visiting=set(); by_name={r['stack']:r for r in rows}
    def visit(name):
        if name in visiting: raise ValueError('Cyclic startup dependency')
        if name in visited: return
        visiting.add(name)
        for dependency in by_name[name]['after']:visit(dependency)
        visiting.remove(name);visited.add(name)
    for name in stacks:visit(name)


def match_live(plan: dict, inventory: dict, excluded_helpers: set[str]) -> dict:
    projects={r['stack']:r for r in plan['stacks']}
    excluded=[];matched=[]
    for container in inventory['containers']:
        name=container['name'].lstrip('/')
        if name in excluded_helpers:
            if container['composeProject'] or container['networkMode']!='none' or container['portBindings'] or any(m['RW'] for m in container['mounts']):
                raise ValueError('Excluded helper must be an isolated, read-only capture helper')
            excluded.append(name);continue
        project=container['composeProject'];service=container['composeService']
        if project not in projects or service not in projects[project]['services']:
            raise ValueError('Live container has no reviewed disposition: '+name)
        matched.append(name)
    if set(excluded)!=excluded_helpers:raise ValueError('Specified helper not present in captured inventory')
    return {'matchedContainers':len(matched),'excludedHelpers':excluded}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-inventory',type=Path)
    parser.add_argument('--exclude-helper',action='append',default=[])
    args=parser.parse_args();here=Path(__file__).resolve().parent;repo=here.parent.parent
    try:
        plan=json.loads((here/'startup-plan.json').read_text())
        paths=subprocess.check_output(['git','-C',str(repo),'ls-files','*docker-compose.yml','*compose.yaml','*compose.yml'],text=True).splitlines()
        definitions={p:yaml.safe_load((repo/p).read_text()) for p in paths}
        validate(plan,{p:sorted(d['services']) for p,d in definitions.items()})
        indicators=[]
        for path,definition in definitions.items():
            if path.startswith('pi/'):continue
            text=json.dumps(definition)
            found=[marker for marker in ('/usr/lib/wsl','/mnt/c','/mnt/e','host.docker.internal') if marker in text]
            if found:indicators.append({'compose':path,'platformReferencesNeedingReview':found})
        result={'coveragePassed':True,'stacks':len(plan['stacks']),'composeServices':sum(len(r['services']) for r in plan['stacks']),'excludedPiDefinitions':len(plan['excludedComposePaths']),'nativePlatformReview':indicators,'nativeDefinitionsAccepted':False,'automaticStartAllowed':False}
        if args.live_inventory:result['liveCoverage']=match_live(plan,json.loads(args.live_inventory.read_text()),set(args.exclude_helper))
        print(json.dumps(result));return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError) as exc:
        print('Startup plan review failed: '+str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
