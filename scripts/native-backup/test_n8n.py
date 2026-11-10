import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import n8n
import repository


class N8nCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root/'source'
        (self.source/'.n8n/binaryData').mkdir(parents=True)
        (self.source/'recovery').mkdir()
        (self.source/'.n8n/config').write_text(json.dumps({'encryptionKey': 'fixture-only-key'}))
        (self.source/'.n8n/binaryData/payload').write_bytes(b'fixture binary')
        self.database = sqlite3.connect(self.source/'.n8n/database.sqlite')
        self.addCleanup(self.database.close)
        self.database.execute('PRAGMA journal_mode=WAL')
        for table in n8n.REQUIRED_TABLES:
            self.database.execute('CREATE TABLE "'+table+'" (id INTEGER PRIMARY KEY, data TEXT)')
            self.database.execute('INSERT INTO "'+table+'" (data) VALUES (?)', ('fixture',))
        self.database.commit()
        # Keep this connection alive: the new rows remain in the live WAL.
        self.database.execute('PRAGMA wal_autocheckpoint=0')
        self.database.execute('INSERT INTO workflow_entity(data) VALUES ("committed WAL row")')
        self.database.commit()
        self.state = {'Id': 'same-container', 'Image': 'same-image', 'RestartCount': 0,
                      'State': {'StartedAt': 'same-start', 'Running': True},
                      'Config': {'Env': []},
                      'Mounts': [{'Source': str(self.source), 'Destination': '/root/.n8n'}]}
        self.state_patch = patch.object(n8n.portainer, 'container_state', return_value=self.state)
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        # Windows lacks chown/xattrs. Linux runs the real ownership/mode checks.
        if n8n.os.name != 'posix':
            self.skipTest('Native Linux metadata and WAL recovery test')

    def capture(self):
        target = self.root/'capture'
        n8n.capture(target, self.source)
        return target

    def test_online_snapshot_includes_live_wal_and_restored_key_and_binary_files(self):
        target = self.capture()
        proof = n8n.inspect_capture(target)
        self.assertEqual(proof['sqliteDatabases']['.n8n/database.sqlite']['tableRowCounts']['workflow_entity'], 2)
        self.assertTrue(proof['pairedEncryptionKeyUnchanged'])
        self.assertNotIn('.n8n/database.sqlite-wal', proof['entries'])
        self.assertNotIn('.n8n/database.sqlite-shm', proof['entries'])
        self.assertEqual((target/'payload/.n8n/binaryData/payload').read_bytes(), b'fixture binary')
        restored = self.root/'restored'
        shutil.copytree(target, restored, copy_function=shutil.copy2)
        self.assertEqual(n8n.inspect_capture(restored)['entries'], proof['entries'])
        self.assertEqual(self.database.execute('SELECT count(*) FROM workflow_entity').fetchone()[0], 2)

    def test_missing_or_changed_key_and_damaged_database_fail_verification(self):
        target = self.capture()
        key = target/'payload/.n8n/config'
        key.write_text('{}')
        with self.assertRaises(ValueError):
            n8n.inspect_capture(target)
        # Another capture is a new, deliberate fixture invocation.
        other = self.root/'second-capture'
        n8n.capture(other, self.source)
        database = other/'payload/.n8n/database.sqlite'
        database.write_bytes(b'broken database')
        with self.assertRaises(ValueError):
            n8n.inspect_capture(other)

    def test_sqlite_attachment_and_its_sidecars_are_preserved_byte_for_byte(self):
        attachment = self.source/'.n8n/binaryData/attachment.sqlite'
        with sqlite3.connect(attachment) as database:
            database.execute('CREATE TABLE attachment(value TEXT)')
            database.execute('INSERT INTO attachment VALUES ("attachment bytes")')
        database.close()
        original = attachment.read_bytes()
        sidecar = Path(str(attachment)+'-wal')
        sidecar.write_bytes(b'attachment sidecar bytes')
        target = self.capture()
        proof = n8n.inspect_capture(target)
        self.assertEqual(set(proof['sqliteDatabases']), {'.n8n/database.sqlite'})
        self.assertEqual((target/'payload/.n8n/binaryData/attachment.sqlite').read_bytes(), original)
        self.assertEqual((target/'payload/.n8n/binaryData/attachment.sqlite-wal').read_bytes(), sidecar.read_bytes())

    def test_source_and_restored_encryption_key_symlinks_are_rejected(self):
        key = self.source/'.n8n/config'
        external = self.root/'external-config'
        key.rename(external)
        key.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'regular files'):
            n8n.capture(self.root/'rejected-symlink', self.source)
        key.unlink()
        key.write_bytes(external.read_bytes())
        target = self.capture()
        restored_key = target/'payload/.n8n/config'
        restored_key.unlink()
        restored_key.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'regular files'):
            n8n.inspect_capture(target)

    def test_existing_destination_and_replaced_runtime_are_not_retried(self):
        target = self.capture()
        with self.assertRaises(FileExistsError):
            n8n.capture(target, self.source)
        changed = {**self.state, 'Id': 'replacement'}
        with patch.object(n8n.portainer, 'container_state', side_effect=[self.state, changed]):
            with self.assertRaisesRegex(ValueError, 'container changed'):
                n8n.capture(self.root/'replaced', self.source)

    def test_external_key_or_wrong_mount_refuses_capture(self):
        self.state['Config']['Env'] = ['N8N_ENCRYPTION_KEY=fixture-external-key']
        with self.assertRaisesRegex(ValueError, 'file-persisted'):
            n8n.capture(self.root/'external', self.source)
        self.state['Config']['Env'] = []
        self.state['Mounts'][0]['Destination'] = '/wrong'
        with self.assertRaisesRegex(ValueError, 'source mount'):
            n8n.capture(self.root/'wrong', self.source)

    def test_changing_supporting_file_and_missing_required_tables_fail(self):
        target = self.root/'file-copy'
        original_stat = Path.stat
        reads = 0
        source = self.source/'.n8n/config'
        def stat(path, *args, **kwargs):
            nonlocal reads
            if path == source:
                reads += 1
                if reads == 2:
                    source.write_text('changed')
            return original_stat(path, *args, **kwargs)
        with patch.object(Path, 'stat', stat):
            with self.assertRaisesRegex(ValueError, 'changed during capture'):
                n8n.stable_copy(source, target)
        source.write_text(json.dumps({'encryptionKey':'fixture-only-key'}))
        self.database.execute('DROP TABLE credentials_entity')
        self.database.commit()
        with self.assertRaisesRegex(ValueError, 'tables are missing'):
            self.capture()

    def test_repository_verifies_restored_database_and_key_before_success(self):
        for tamper in [False, True]:
            with self.subTest(tamper=tamper):
                state = self.root/('jobs-tampered' if tamper else 'jobs-valid')
                config = {'scope': 'n8n', 'stateDirectory': str(state), 'applyRetention': False}
                captured = []
                real_capture = n8n.capture
                def capture(destination):
                    captured.append(destination)
                    return real_capture(destination, self.source)
                def restic(*arguments):
                    if arguments[0] == 'backup':
                        self.assertIn('scope=n8n', arguments)
                        return json.dumps({'message_type': 'summary', 'snapshot_id': 'a'*64})
                    if arguments[0] == 'restore':
                        target = Path(arguments[arguments.index('--target')+1])/captured[0].relative_to(captured[0].anchor)
                        shutil.copytree(captured[0], target, copy_function=shutil.copy2)
                        if tamper:
                            (target/'payload/.n8n/config').write_text('{}')
                    return ''
                with patch.object(repository.Repository, 'verify_identity'), \
                     patch.object(repository.Repository, 'run', side_effect=restic), \
                     patch.object(repository.Repository, 'retention', return_value={'mode':'dry_run'}), \
                     patch.object(repository.n8n, 'capture', side_effect=capture), \
                     patch.object(repository, 'notify') as alert:
                    if tamper:
                        with self.assertRaisesRegex(RuntimeError, 'Native backup failed'):
                            repository.run(config)
                        alert.assert_called_once_with(config, False)
                    else:
                        self.assertTrue(repository.run(config)['success'])
                        alert.assert_called_once_with(config, True)


if __name__ == '__main__':
    unittest.main()

