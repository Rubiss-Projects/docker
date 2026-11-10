import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('native_compose', Path(__file__).with_name('compose.py'))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
PIN = 'vendor/app:1.2.3@sha256:'+'a'*64
LOCAL = 'sha256:'+'b'*64


def fixture():
    source = {'name':'example', 'services':{'app':{'image':PIN,
        'environment':{'APPLICATION_KEY':'initial'}, 'labels':{'homepage.name':'Example'},
        'volumes':[{'type':'bind','source':'/srv/Docker/example/config','target':'/config','bind':{'create_host_path':True}}],
        'networks':{'proxynet':None}}}, 'networks':{'proxynet':{'name':'proxynet','external':True}}}
    native = copy.deepcopy(source)
    native['services']['app']['volumes'] = [{'type':'volume','source':'accepted','target':'/config'}]
    native['volumes'] = {'accepted':{'name':'existing-native-state','external':True}}
    native['services']['app']['network_mode'] = 'host'
    native['services']['app'].pop('networks')
    rule = {'services':{'app':{'image':{'source':PIN,'local':LOCAL},'fields':{
        key:{'sourceSha256':deploy.digest(deploy.field_value(source['services']['app'],key)),
             **deploy.field_value(native['services']['app'],key)} for key in deploy.PROTECTED_FIELDS},'removeLabels':[]}},
        'sourceResourcesSha256':deploy.digest({k:source.get(k,{}) for k in ['volumes','networks']}),
        'resources':{k:native.get(k,{}) for k in ['volumes','networks']}}
    return source, native, rule


class NativeRecipeTests(unittest.TestCase):
    def test_current_source_updates_retain_accepted_storage_and_host_network(self):
        source,native,rule=fixture();source['services']['app']['environment']['APPLICATION_KEY']='rotated'
        source['services']['app']['labels']['homepage.name']='Updated name'
        result,local=deploy.compile_recipe(source,rule)
        self.assertEqual(result['services']['app']['volumes'],native['services']['app']['volumes'])
        self.assertEqual(result['services']['app']['network_mode'],'host')
        self.assertNotIn('networks',result['services']['app'])
        self.assertEqual(result['services']['app']['environment']['APPLICATION_KEY'],'rotated')
        self.assertEqual(result['services']['app']['labels']['homepage.name'],'Updated name')
        self.assertEqual(result['services']['app']['image'],LOCAL);self.assertEqual(local,{'app'})
        self.assertEqual(source['services']['app']['image'],PIN)

    def test_new_registry_pin_is_pulled_and_not_frozen_to_the_imported_image(self):
        source,_,rule=fixture();new='vendor/app:1.2.4@sha256:'+'c'*64;source['services']['app']['image']=new
        result,local=deploy.compile_recipe(source,rule)
        self.assertEqual(result['services']['app']['image'],new);self.assertEqual(local,set())
        self.assertEqual(deploy.compose_arguments(['pull','--ignore-buildable'],{'app'},local),['pull','--ignore-buildable','app'])
        self.assertIsNone(deploy.compose_arguments(['pull','--ignore-buildable'],{'app'},{'app'}))

    def test_changed_volume_network_security_or_command_requires_acceptance(self):
        for field,value in [('volumes',[]),('networks',{}),('security_opt',['apparmor=unconfined']),('entrypoint',['unexpected']),('build',{'context':'.'})]:
            with self.subTest(field=field):
                source,_,rule=fixture();source['services']['app'][field]=value
                with self.assertRaises(ValueError):deploy.compile_recipe(source,rule)

    def test_unknown_service_or_changed_network_definition_fails_before_operations(self):
        source,_,rule=fixture();source['services']['extra']={'image':PIN}
        with self.assertRaises(ValueError):deploy.compile_recipe(source,rule)
        source,_,rule=fixture();source['networks']['proxynet']['name']='different-network'
        with self.assertRaises(ValueError):deploy.compile_recipe(source,rule)

    def test_missing_policy_field_coverage_is_not_an_implicit_allow(self):
        source,_,rule=fixture();rule['services']['app']['fields'].pop('volumes')
        with self.assertRaises(ValueError):deploy.compile_recipe(source,rule)

    def test_unpinned_images_are_rejected_and_bind_path_creation_is_disabled(self):
        source,_,rule=fixture();source['services']['app']['image']='vendor/app:latest'
        with self.assertRaises(ValueError):deploy.compile_recipe(source,rule)
        source,_,rule=fixture();rule['services']['app']['fields']['volumes'].update(present=True,value=source['services']['app']['volumes'])
        result,_=deploy.compile_recipe(source,rule)
        self.assertFalse(result['services']['app']['volumes'][0]['bind']['create_host_path'])

    def test_native_commands_cannot_start_unreleased_service_keys_or_remove_volumes(self):
        self.assertEqual(deploy.compose_arguments(['up','-d','--no-build'],{'app'},set()),['up','-d','--no-build','app'])
        with self.assertRaises(ValueError):deploy.compose_arguments(['down','-v'],{'app'},set())
        with self.assertRaises(ValueError):deploy.compose_arguments(['up','-d','dormant-game'],{'app'},set())

    def test_database_upgrade_keeps_its_explicit_service_selection(self):
        command=['up','-d','--no-deps','--wait','--wait-timeout','180','database']
        self.assertEqual(deploy.compose_arguments(command,{'app','database'},set()),command)
        self.assertEqual(deploy.compose_arguments(['stop','app'],{'app','database'},set()),['stop','app'])
        self.assertEqual(deploy.compose_arguments(['exec','-T','database','psql','-X'],{'app','database'},set()),['exec','-T','database','psql','-X'])
        with self.assertRaises(ValueError):deploy.compose_arguments(['exec','-T','unreleased','sh'],{'app'},set())

    def test_existing_unadmitted_project_container_is_rejected_before_remove_orphans(self):
        def capture(command):
            return b'unknown-id' if command[1]=='ps' else json.dumps([{'Config':{'Labels':{'com.docker.compose.service':'old-extra'}}}]).encode()
        with patch.object(deploy,'capture',side_effect=capture),self.assertRaises(ValueError):deploy.validate_project('example',{'app'})

    def test_recreated_volume_or_bridge_requires_fresh_native_acceptance(self):
        recipe={'services':{'app':{'volumes':[{'type':'volume','source':'state','target':'/config'}]}},
                'volumes':{'state':{'name':'existing-state','external':True}}}
        with patch.object(deploy,'capture',return_value=json.dumps([{'Name':'existing-state','Driver':'local','CreatedAt':'new'}]).encode()),self.assertRaises(ValueError):
            deploy.validate_resources(recipe,set(),{'volumes':{'state':'original'},'networks':{}})
        recipe={'services':{'app':{'networks':{'proxynet':None}}},'networks':{'proxynet':{'name':'proxynet'}}}
        with patch.object(deploy,'capture',return_value=json.dumps([{'Driver':'bridge','Internal':False,'Id':'new-bridge'}]).encode()),self.assertRaises(ValueError):
            deploy.validate_resources(recipe,set(),{'volumes':{},'networks':{'proxynet':'accepted-bridge'}})

    @unittest.skipUnless(hasattr(os,'geteuid'), 'Native file permissions require Linux')
    def test_secret_containing_recipes_are_written_privately_and_atomically(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);root.chmod(0o700)
            with patch.object(deploy,'STATE',root):path=deploy.write_recipe('example',{'services':{'app':{'environment':{'KEY':'private'}}}})
            self.assertEqual(json.loads(path.read_text())['services']['app']['environment']['KEY'],'private')
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(list(root.iterdir()),[path])


if __name__ == '__main__':unittest.main()
