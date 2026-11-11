import copy
import unittest
from unittest.mock import patch

import native_ups_guard as guard
from native_ups_restore import select_stopped


class RestoreSelectionTests(unittest.TestCase):
    def setUp(self):
        self.cid = 'a' * 64
        self.saved = {'id': self.cid, 'image': 'sha256:' + 'b' * 64,
                      'project': 'plex', 'service': 'plex'}
        self.manifest = {'version': 1, 'boot': 'previous-boot', 'containers': [self.saved]}
        self.current = [{'Id': self.cid, 'Image': self.saved['image'], 'State': {'Running': False},
                         'Config': {'Labels': {'com.docker.compose.project': 'plex',
                                               'com.docker.compose.service': 'plex'}}}]
        self.policy = {'stacks': {'plex': {'services': {'plex': {}}}}}

    def test_only_previously_running_exact_id_is_selected(self):
        dormant = copy.deepcopy(self.current[0]);dormant['Id'] = 'c' * 64
        self.assertEqual(select_stopped(self.manifest, self.current + [dormant], self.policy, 'new-boot'), [self.cid])
        self.current[0]['State']['Running'] = True
        self.assertEqual(select_stopped(self.manifest, self.current, self.policy, 'new-boot'), [])

    def test_missing_changed_or_unadmitted_identity_holds_recovery(self):
        for change in ['missing', 'image', 'owner', 'policy', 'same-boot', 'duplicate']:
            with self.subTest(change=change):
                rows=copy.deepcopy(self.current);manifest=copy.deepcopy(self.manifest);policy=copy.deepcopy(self.policy);boot='new-boot'
                if change=='missing':rows=[]
                if change=='image':rows[0]['Image']='sha256:'+'d'*64
                if change=='owner':rows[0]['Config']['Labels']['com.docker.compose.service']='other'
                if change=='policy':policy={'stacks':{}}
                if change=='same-boot':boot=manifest['boot']
                if change=='duplicate':manifest['containers'].append(copy.deepcopy(self.saved))
                with self.assertRaises(ValueError):select_stopped(manifest,rows,policy,boot)

    def test_manifest_does_not_restore_unmanaged_temporary_containers(self):
        unmanaged=copy.deepcopy(self.current[0]);unmanaged['Config']['Labels']={}
        with patch.object(guard.subprocess,'check_output',return_value=__import__('json').dumps(self.current+[unmanaged]).encode()), patch.object(guard,'write_state') as write:
            guard.capture_restore_manifest([self.cid,'c'*64],'old-boot')
            self.assertEqual(write.call_args.args[1]['containers'],[self.saved])


if __name__ == '__main__':
    unittest.main()
