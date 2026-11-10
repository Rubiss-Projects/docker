import os
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from confined_files import SafeTree, snapshot_connection, sqlite_snapshot_file
import host_files


class SQLiteReadSnapshotTests(unittest.TestCase):
    def test_concurrent_wal_commit_does_not_restart_or_enter_the_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'database'
            with closing(sqlite3.connect(path)) as writer:
                writer.execute('PRAGMA page_size=2048')
                writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('CREATE TABLE state(value BLOB)')
                writer.executemany('INSERT INTO state VALUES (?)', [(b'x'*4096,)]*64)
                writer.commit()
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(':memory:')) as target:
                    injected = []
                    def progress(status, remaining, total):
                        if not injected and status == sqlite3.SQLITE_OK:
                            writer.execute("INSERT INTO state VALUES ('committed during backup')")
                            writer.commit();injected.append(True)
                    snapshot_connection(source, target, progress, pages=1)
                    self.assertTrue(injected)
                    self.assertEqual(target.execute('PRAGMA page_size').fetchone()[0], 2048)
                    self.assertEqual(target.execute('SELECT count(*) FROM state').fetchone()[0], 64)
                    self.assertEqual(writer.execute('SELECT count(*) FROM state').fetchone()[0], 65)
                    self.assertFalse(source.in_transaction)


@unittest.skipUnless(sys.platform == 'linux' and getattr(os, 'geteuid', lambda: -1)() == 0,
                     'Host file confinement requires native Linux root')
class HostFileCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base/'source';self.source.mkdir()
        self.target = self.base/'target';self.target.mkdir()
        (self.source/'keys').mkdir()
        (self.source/'keys/identity').write_bytes(b'fixture secret')
        (self.source/'keys/identity').chmod(0o600)
        os.chown(self.source/'keys/identity', 1000, 1000)

    def test_unknown_sqlite_extension_uses_committed_wal_snapshot_and_preserves_links(self):
        database = sqlite3.connect(self.source/'state.cache')
        self.addCleanup(database.close)
        database.execute('PRAGMA journal_mode=WAL')
        database.execute('CREATE TABLE state(value TEXT)')
        database.executemany('INSERT INTO state VALUES (?)', [('first',), ('second',)])
        database.commit()
        database.execute("INSERT INTO state VALUES ('uncommitted')")
        outside = self.base/'outside';outside.write_bytes(b'must not be read through link')
        (self.source/'outside-link').symlink_to(outside)
        proof = host_files.capture_tree(self.source, self.target)
        self.assertEqual(proof['sqliteDatabases']['state.cache']['tableRowCounts'], {'state': 2})
        self.assertEqual(proof['entries']['keys/identity']['uid'], 1000)
        self.assertEqual(proof['entries']['keys/identity']['mode'], 0o600)
        self.assertEqual((self.target/'outside-link').readlink(), outside)
        self.assertNotIn('state.cache-wal', proof['entries'])
        self.assertNotIn('state.cache-shm', proof['entries'])
        self.assertTrue(proof['excludedTransientEntries'])
        self.assertEqual(outside.read_bytes(), b'must not be read through link')
        host_files.inspect_tree(self.target, proof)

    def test_changed_restored_key_or_metadata_is_rejected(self):
        proof = host_files.capture_tree(self.source, self.target)
        path = self.target/'keys/identity'
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'metadata differs'):
            host_files.inspect_tree(self.target, proof)
        path.write_bytes(b'changed key')
        with self.assertRaisesRegex(ValueError, 'file differs'):
            host_files.inspect_tree(self.target, proof)

    def test_new_special_file_requires_disposition_before_capture_can_pass(self):
        os.mkfifo(self.source/'unexpected-pipe')
        with self.assertRaisesRegex(ValueError, 'special file'):
            host_files.capture_tree(self.source, self.target)

    def test_snapshot_file_refuses_symlink_destination_without_modifying_target(self):
        database = sqlite3.connect(self.source/'state')
        database.execute('CREATE TABLE state(value TEXT)');database.commit();database.close()
        outside = self.base/'outside';outside.write_bytes(b'intact')
        (self.target/'state').symlink_to(outside)
        with SafeTree(self.source) as source, SafeTree(self.target) as target:
            with self.assertRaises(OSError):
                sqlite_snapshot_file(source, 'state', target, 'state')
        self.assertEqual(outside.read_bytes(), b'intact')

    def test_large_source_fails_before_allocating_or_creating_a_snapshot(self):
        with (self.source/'oversized').open('wb') as stream:
            stream.truncate(1024**3+1)
        with SafeTree(self.source) as source, SafeTree(self.target) as target:
            with self.assertRaisesRegex(ValueError, '1 GiB'):
                sqlite_snapshot_file(source, 'oversized', target, 'snapshot')
        self.assertFalse((self.target/'snapshot').exists())

    def test_whole_host_root_cannot_be_used_as_a_sqlite_sandbox(self):
        with self.assertRaisesRegex(ValueError, 'confinement boundary'):
            host_files.capture_tree(Path('/'), self.target)


if __name__ == '__main__':
    unittest.main()
