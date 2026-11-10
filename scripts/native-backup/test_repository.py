import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import repository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.mount = self.root/'mount'
        self.repo = self.mount/'repo'
        self.repo.mkdir(parents=True)
        self.config = {'mountTarget': str(self.mount), 'mountSource': '//nas/Recovery',
                       'mountType': 'cifs', 'repository': str(self.repo),
                       'minimumFreeBytes': 100, 'passwordFile': '/private/password',
                       'commandTimeoutSeconds': 60}

    def mount_row(self, **changes):
        row = {'target': str(self.mount), 'source': '//nas/Recovery',
               'fstype': 'cifs', 'options': 'rw,relatime'}
        row.update(changes)
        return json.dumps({'filesystems': [row]}).encode()

    def test_missing_or_replaced_nas_mount_never_runs_restic(self):
        job = repository.Repository(self.config, self.root)
        for changes in [{'target': '/'}, {'source': '//other/Recovery'},
                        {'fstype': 'ext4'}, {'options': 'ro'}]:
            with self.subTest(changes=changes), \
                 patch.object(repository.subprocess, 'check_output', return_value=self.mount_row(**changes)), \
                 patch.object(repository.subprocess, 'run') as restic:
                with self.assertRaises(ValueError):
                    job.run('snapshots')
                restic.assert_not_called()

    def test_guard_accepts_exact_mount_and_checks_headroom(self):
        with patch.object(repository.subprocess, 'check_output', return_value=self.mount_row()), \
             patch.object(repository.os, 'statvfs', create=True,
                          return_value=SimpleNamespace(f_bavail=100, f_frsize=10)):
            repository.guard_mount(self.config)
            with patch.object(repository.os, 'statvfs', create=True,
                              return_value=SimpleNamespace(f_bavail=1, f_frsize=10)):
                with self.assertRaisesRegex(ValueError, 'headroom'):
                    repository.guard_mount(self.config)

    def test_repository_outside_share_is_rejected(self):
        self.config['repository'] = str(self.root)
        with patch.object(repository.subprocess, 'check_output', return_value=self.mount_row()):
            with self.assertRaisesRegex(ValueError, 'inside'):
                repository.guard_mount(self.config)

    def test_each_command_revalidates_mount_and_persists_failures(self):
        with patch.object(repository, 'guard_mount') as guard, \
             patch.object(repository.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 1, 'partial', 'failed')) as command:
            job = repository.Repository(self.config, self.root)
            with self.assertRaisesRegex(RuntimeError, 'reconcile'):
                job.run('backup', '/private/capture')
            guard.assert_called_once_with(self.config)
            self.assertEqual((self.root/'restic-1.stderr').read_text(), 'failed')
            self.assertIn('--no-cache', command.call_args.args[0])
            self.assertEqual(command.call_args.kwargs['env']['GODEBUG'], 'asyncpreemptoff=1')

    def test_retention_requires_both_owned_tags_and_never_deletes(self):
        job = repository.Repository(self.config, self.root)
        with patch.object(job, 'run', return_value='[]') as command:
            result = job.retention()
            arguments = command.call_args.args
            self.assertIn('--dry-run', arguments)
            self.assertEqual(arguments[arguments.index('--tag')+1], 'native-recurring,scope=portainer')
            self.assertFalse(result['deletionPerformed'])
            self.assertNotIn('prune', arguments)

    def test_retention_rejects_any_migration_or_other_host_candidate(self):
        job = repository.Repository(self.config, self.root)
        for row in [{'hostname': 'ben-server', 'tags': ['admitted-migration']},
                    {'hostname': 'other-host', 'tags': ['native-recurring', 'scope=portainer']}]:
            with self.subTest(row=row), patch.object(job, 'run', return_value=json.dumps([{'remove': [row]}])):
                with self.assertRaisesRegex(ValueError, 'unowned'):
                    job.retention()

    def test_wrong_encrypted_repository_identity_is_rejected(self):
        self.config['repositoryId'] = 'expected'
        job = repository.Repository(self.config, self.root)
        with patch.object(job, 'run', return_value='{"id":"different"}'):
            with self.assertRaisesRegex(ValueError, 'identity'):
                job.verify_identity()

    def test_scope_retention_cannot_select_another_application(self):
        for scope in ['n8n', 'vault']:
            config = {**self.config, 'scope': scope}
            job = repository.Repository(config, self.root)
            with self.subTest(scope=scope), patch.object(job, 'run', return_value='[]') as command:
                job.retention()
                self.assertIn('native-recurring,scope='+scope, command.call_args.args)
            row = {'id': 'a'*64, 'hostname': 'ben-server', 'tags': ['native-recurring', 'scope=portainer']}
            with patch.object(job, 'run', return_value=json.dumps([{'remove': [row]}])):
                with self.assertRaisesRegex(ValueError, 'unowned'):
                    job.retention(apply=True)

    def test_retention_applies_only_exact_owned_ids_and_preserves_migration_inventory(self):
        removed = {'id': 'a'*64, 'hostname': 'ben-server', 'tags': ['native-recurring', 'scope=portainer']}
        kept = {**removed, 'id': 'b'*64}
        migration = {'id': 'c'*64, 'hostname': 'ben-server', 'tags': ['admitted-migration']}
        after = json.dumps([kept, migration])
        job = repository.Repository(self.config, self.root)
        with patch.object(job, 'run', side_effect=[json.dumps([{'remove': [removed]}]),
                json.dumps([removed, kept, migration]), '', after, '', '', after]) as command:
            result = job.retention(apply=True)
            self.assertEqual(command.call_args_list[2].args, ('forget', 'a'*64))
            self.assertEqual(command.call_args_list[4].args, ('prune', '--max-repack-size', '1G'))
            self.assertTrue(result['allUnselectedSnapshotsRetained'])
            intent = json.loads((self.root/'retention-execution-intent.json').read_text())
            self.assertEqual(set(intent['preserveSnapshotIds']), {'b'*64, 'c'*64})

    def test_last_owned_snapshot_is_never_removed(self):
        row = {'id': 'a'*64, 'hostname': 'ben-server', 'tags': ['native-recurring', 'scope=portainer']}
        job = repository.Repository(self.config, self.root)
        with patch.object(job, 'run', side_effect=[json.dumps([{'remove': [row]}]), json.dumps([row])]) as command:
            with self.assertRaisesRegex(ValueError, 'preserve a snapshot'):
                job.retention(apply=True)
            self.assertEqual(command.call_count, 2)

    @unittest.skipIf(repository.fcntl is None, 'Linux flock admission test')
    def test_uncertain_capture_is_alerted_and_blocks_automatic_api_replay(self):
        tool = self.root/'bbolt'
        tool.write_bytes(b'test verifier')
        self.config.update(stateDirectory=str(self.root/'jobs'), bbolt=str(tool), applyRetention=False)
        with patch.object(repository.Repository, 'verify_identity'), \
             patch.object(repository.portainer, 'BBOLT_SHA256', hashlib.sha256(tool.read_bytes()).hexdigest()), \
             patch.object(repository.portainer, 'capture', side_effect=TimeoutError) as capture, \
             patch.object(repository, 'notify') as alert:
            with self.assertRaisesRegex(RuntimeError, 'Native backup failed'):
                repository.run(self.config)
            self.assertTrue((self.root/'jobs/capture-attention.json').is_file())
            with self.assertRaisesRegex(RuntimeError, 'Reconcile'):
                repository.run(self.config)
            capture.assert_called_once()
            self.assertEqual([call.args[1] for call in alert.call_args_list], [False, False])

    @unittest.skipIf(repository.fcntl is None, 'Linux process termination admission test')
    def test_terminated_capture_persists_admission_and_prevents_another_api_request(self):
        tool = self.root/'bbolt'
        tool.write_bytes(b'test verifier')
        program = '''import hashlib,json,sys,time
from pathlib import Path
import repository
config=json.loads(sys.argv[1])
repository.Repository.verify_identity=lambda self:None
repository.portainer.BBOLT_SHA256=hashlib.sha256(Path(config['bbolt']).read_bytes()).hexdigest()
repository.notify=lambda config,success:None
def capture(destination,tool):
 Path(config['ready']).write_text('inside capture')
 while True:time.sleep(.05)
repository.portainer.capture=capture
repository.run(config)
'''
        for termination in ['terminate', 'kill']:
            with self.subTest(termination=termination):
                state = self.root/termination
                ready = self.root/(termination+'-ready')
                config = {**self.config, 'stateDirectory': str(state),
                          'bbolt': str(tool), 'applyRetention': False, 'ready': str(ready)}
                child = subprocess.Popen([sys.executable, '-B', '-c', program, json.dumps(config)],
                                         cwd=Path(repository.__file__).parent,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    deadline = time.monotonic()+10
                    while not ready.exists() and child.poll() is None and time.monotonic()<deadline:
                        time.sleep(.02)
                    self.assertTrue(ready.exists(), 'Child never entered mocked capture')
                    getattr(child, termination)()
                    child.communicate(timeout=5)
                    self.assertNotEqual(child.returncode, 0)
                    self.assertTrue((state/'capture-attention.json').is_file())
                    with patch.object(repository, 'notify'), \
                         patch.object(repository.portainer, 'capture') as capture:
                        with self.assertRaisesRegex(RuntimeError, 'Reconcile'):
                            repository.run(config)
                        capture.assert_not_called()
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.communicate(timeout=5)

    @unittest.skipIf(repository.fcntl is None, 'Linux successful admission completion test')
    def test_completed_capture_clears_durable_admission_before_backup(self):
        state = self.root/'jobs'
        tool = self.root/'bbolt'
        tool.write_bytes(b'test verifier')
        config = {**self.config, 'stateDirectory': str(state), 'bbolt': str(tool), 'applyRetention': False}
        content = b'fixture archive'
        proof = {'archiveSha256': hashlib.sha256(content).hexdigest(), 'files': {'portainer.db': {'bytes': 1}}}
        captured = []
        def capture(destination, verifier):
            self.assertTrue((state/'capture-attention.json').is_file())
            destination.mkdir()
            (destination/'backup.tar.gz').write_bytes(content)
            captured.append(destination)
            return proof
        def restic(*arguments):
            self.assertFalse((state/'capture-attention.json').exists())
            if arguments[0] == 'backup':
                return json.dumps({'message_type': 'summary', 'snapshot_id': 'a'*64})
            if arguments[0] == 'restore':
                target = Path(arguments[arguments.index('--target')+1])/captured[0].relative_to(captured[0].anchor)
                target.mkdir(parents=True)
                (target/'backup.tar.gz').write_bytes(content)
            return ''
        with patch.object(repository.Repository, 'verify_identity'), \
             patch.object(repository.Repository, 'run', side_effect=restic), \
             patch.object(repository.Repository, 'retention', return_value={'mode':'dry_run'}), \
             patch.object(repository.portainer, 'BBOLT_SHA256', hashlib.sha256(tool.read_bytes()).hexdigest()), \
             patch.object(repository.portainer, 'capture', side_effect=capture), \
             patch.object(repository.portainer, 'inspect_archive', return_value=proof), \
             patch.object(repository, 'notify') as alert:
            result = repository.run(config)
            self.assertTrue(result['success'])
            self.assertFalse((state/'capture-attention.json').exists())
            alert.assert_called_once_with(config, True)

    @unittest.skipIf(repository.fcntl is None, 'Linux repository job locking')
    def test_vault_success_heartbeat_requires_an_actual_database_restore(self):
        config = {**self.config, 'scope': 'vault', 'applyRetention': False,
                  'stateDirectory': str(self.root/'vault-jobs')}
        def restic(*arguments):
            if arguments[0] == 'backup':
                return json.dumps({'message_type': 'summary', 'snapshot_id': 'a'*64})
            return ''
        with patch.object(repository.Repository, 'verify_identity'), \
             patch.object(repository.Repository, 'run', side_effect=restic), \
             patch.object(repository.Repository, 'retention') as retention, \
             patch.object(repository.vault, 'capture', return_value={'fixture': True}), \
             patch.object(repository.vault, 'inspect_capture', return_value={'fixture': True}), \
             patch.object(repository.vault, 'verify_database', side_effect=ValueError('fixture restore failed')), \
             patch.object(repository, 'notify') as alert:
            with self.assertRaisesRegex(RuntimeError, 'Native backup failed'):
                repository.run(config)
            alert.assert_called_once_with(config, False)
            retention.assert_not_called()
        latest = json.loads((self.root/'vault-jobs/latest.json').read_text())
        self.assertFalse(latest['success'])
        self.assertEqual(latest['failedAtPhase'], 'restore_verification')

    def test_push_delivery_errors_never_print_token_bearing_url(self):
        token_file = self.root/'push-url'
        url = 'http://127.0.0.1:3001/api/push/private-token'
        token_file.write_text(url)
        self.config['pushUrlFile'] = str(token_file)
        with patch.object(repository.urllib.request.OpenerDirector, 'open', side_effect=RuntimeError(url)):
            with self.assertRaisesRegex(RuntimeError, '^Backup monitor delivery failed$') as error:
                repository.notify(self.config, False)
            self.assertNotIn('private-token', str(error.exception))

    def test_push_only_uses_local_monitor_without_redirects(self):
        token_file = self.root/'push-url'
        self.config['pushUrlFile'] = str(token_file)
        for url in ['https://example.com/api/push/token', 'http://127.0.0.1:3001/api/push/token?status=up',
                    'http://user:password@127.0.0.1:3001/api/push/token']:
            token_file.write_text(url)
            with self.subTest(url=url), self.assertRaises(ValueError):
                repository.notify(self.config, True)


if __name__ == '__main__':
    unittest.main()
