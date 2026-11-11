import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_ups_guard as guard
import native_ups_restore as restore
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
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(guard, 'ROOT', Path(directory)), \
                patch.object(guard.subprocess, 'check_output', return_value=json.dumps(self.current+[unmanaged]).encode()), \
                patch.object(guard, 'write_state') as write:
            guard.capture_restore_manifest([self.cid,'c'*64],'old-boot')
            self.assertEqual(write.call_args.args[1]['containers'],[self.saved])

    def test_second_outage_keeps_identities_still_waiting_for_recovery(self):
        second = copy.deepcopy(self.current[0])
        second['Id'] = 'c' * 64
        with tempfile.TemporaryDirectory() as directory, patch.object(guard, 'ROOT', Path(directory)):
            with patch.object(guard.subprocess, 'check_output', return_value=json.dumps(self.current+[second]).encode()):
                guard.capture_restore_manifest([self.cid, second['Id']], 'first-outage-boot')
            with patch.object(guard.subprocess, 'check_output', return_value=json.dumps(self.current).encode()):
                guard.capture_restore_manifest([self.cid], 'interrupted-recovery-boot')
            saved = json.loads((Path(directory) / 'restore-pending.json').read_text())
            self.assertEqual(saved['boot'], 'interrupted-recovery-boot')
            self.assertEqual({row['id'] for row in saved['containers']}, {self.cid, second['Id']})
            self.assertEqual(select_stopped(saved, self.current+[second], self.policy, 'next-boot'),
                             [self.cid, second['Id']])

    def test_new_shutdown_intent_holds_recovery_even_after_power_returns(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(restore, 'ROOT', Path(directory)), \
                patch.object(restore, 'load_manifest', return_value={'boot': 'current-boot'}), \
                patch.object(restore, 'sample', return_value='OL') as sample:
            (Path(directory) / 'shutdown-intent.json').touch()
            with self.assertRaisesRegex(ValueError, 'already committed'):
                restore.require_online('current-boot')
            sample.assert_not_called()


if __name__ == '__main__':
    unittest.main()
