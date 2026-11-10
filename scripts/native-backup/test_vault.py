import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from confined_files import SafeTree
import vault


class VaultTableProofTests(unittest.TestCase):
    def test_table_identity_with_dots_newlines_and_pipes_is_unambiguous(self):
        rows = [['public', 'User', '2', 'a'*32],
                ['a.b', 'c\n|d', '0', 'b'*32], ['a', 'b.c\n|d', '1', 'c'*32]]
        value = vault.table_inventory(('\n'.join(json.dumps(r) for r in rows)+'\n').encode())
        self.assertEqual(len(value), 3)
        self.assertEqual(value['["public","User"]']['rows'], 2)

    def test_duplicate_malformed_or_empty_table_proofs_are_rejected(self):
        row = json.dumps(['public', 'User', '1', 'a'*32])
        for data in [b'', (row+'\n'+row).encode(),
                     json.dumps(['public', 'User', '-1', 'a'*32]).encode(),
                     json.dumps(['public', 'User', '1', 'bad']).encode()]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                vault.table_inventory(data)

    def test_an_empty_or_wrong_database_cannot_count_as_a_vault_restore(self):
        with self.assertRaisesRegex(ValueError, 'application tables'):
            vault.require_vault_tables({'["public","Other"]': {}})
        vault.require_vault_tables({'["public","User"]': {}, '["public","Cipher"]': {}})

    def test_any_uncertain_restore_helper_blocks_a_new_capture_before_admission(self):
        with patch.object(vault, 'command', return_value=b'abc\n'), \
             patch.object(vault.os, 'geteuid', return_value=0, create=True), \
             patch.object(vault.os, 'umask', return_value=0), \
             patch.object(vault, 'admit') as admit:
            with self.assertRaisesRegex(RuntimeError, 'retained vault restore helper'):
                vault.capture(Path('/unused'))
            admit.assert_not_called()


@unittest.skipUnless(sys.platform == 'linux' and getattr(os, 'geteuid', lambda: -1)() == 0,
                     'Confined file tests require native Linux root')
class VaultFileProofTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in ['Web', 'data-protection', 'attachments/client/logs', 'logs']:
            (self.root/name).mkdir(parents=True, exist_ok=True)
        for name in ['identity.pfx', 'Web/app-id.json', 'data-protection/key-fixture.xml',
                     'attachments/client/logs/identity.pfx', 'logs/changing.log']:
            (self.root/name).write_bytes(b'fixture')

    def test_only_the_root_log_directory_is_excluded(self):
        with SafeTree(self.root) as tree:
            result = vault.file_inventory(tree)
        self.assertNotIn('logs', result)
        self.assertNotIn('logs/changing.log', result)
        self.assertIn('attachments/client/logs/identity.pfx', result)

    def test_missing_or_empty_identity_material_is_rejected(self):
        for name in ['identity.pfx', 'Web/app-id.json', 'data-protection/key-fixture.xml']:
            path = self.root/name
            previous = path.read_bytes()
            path.write_bytes(b'')
            with self.subTest(name=name), SafeTree(self.root) as tree, self.assertRaises(ValueError):
                vault.file_inventory(tree)
            path.write_bytes(previous)

    def test_external_key_symlinks_are_rejected(self):
        (self.root/'identity.pfx').unlink()
        (self.root/'identity.pfx').symlink_to('/etc/passwd')
        with SafeTree(self.root) as tree, self.assertRaises(ValueError):
            vault.file_inventory(tree)

    def test_logs_symlink_is_not_silently_omitted(self):
        (self.root/'logs/changing.log').unlink()
        (self.root/'logs').rmdir()
        (self.root/'logs').symlink_to('/etc')
        with SafeTree(self.root) as tree, self.assertRaises(ValueError):
            vault.file_inventory(tree)


if __name__ == '__main__':
    unittest.main()
