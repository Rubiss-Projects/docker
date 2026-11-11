import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('checkout_permissions', Path(__file__).with_name('checkout_permissions.py'))
permissions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(permissions)


@unittest.skipUnless(os.name == 'posix', 'Native Unix permissions')
class CheckoutPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo'
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)

    def stage(self):
        subprocess.run(['git', '-C', str(self.repo), '-c', 'filter.git-crypt.clean=cat',
                        '-c', 'filter.git-crypt.required=false', 'add', '.'], check=True)

    def test_repairs_public_executable_and_encrypted_files_without_content_changes(self):
        (self.repo / '.gitattributes').write_text('*.env.secret filter=git-crypt\n')
        script = self.repo / 'run.sh';script.write_text('#!/bin/sh\nexit 0\n');script.chmod(0o755)
        secret = self.repo / 'app.env.secret';secret.write_text('test fixture, not a credential\n')
        self.stage()
        for path in [self.repo, script, secret]:path.chmod(0o777)
        permissions.apply(permissions.plan(self.repo))
        self.assertEqual(self.repo.stat().st_mode & 0o777, 0o755)
        self.assertEqual(script.stat().st_mode & 0o777, 0o755)
        self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
        self.assertEqual(secret.read_text(), 'test fixture, not a credential\n')
        self.assertTrue(all(c.path.lstat().st_mode & 0o777 == c.mode for c in permissions.plan(self.repo)))

    def test_untracked_application_data_and_public_symlink_target_are_untouched(self):
        source = self.repo / 'app';source.mkdir();(source / 'config.yml').write_text('enabled: true\n')
        target = Path(self.temp.name) / 'outside';target.write_text('retained');target.chmod(0o777)
        (self.repo / 'reference').symlink_to(target)
        self.stage()
        data = source / 'runtime.db';data.write_text('retained application data');data.chmod(0o777)
        permissions.apply(permissions.plan(self.repo))
        self.assertEqual(data.stat().st_mode & 0o777, 0o777)
        self.assertEqual(target.stat().st_mode & 0o777, 0o777)
        self.assertTrue((self.repo / 'reference').is_symlink())

    def test_git_metadata_and_local_encryption_key_are_private(self):
        (self.repo / 'source.txt').write_text('source');self.stage()
        keys = self.repo / '.git/git-crypt/keys';keys.mkdir(parents=True)
        key = keys / 'default';key.write_text('test key fixture')
        for path in [self.repo / '.git', keys.parent, keys, key]:path.chmod(0o777)
        permissions.apply(permissions.plan(self.repo))
        for path in [self.repo / '.git', keys.parent, keys]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        self.assertEqual(key.read_text(), 'test key fixture')

    def test_symlinked_parent_rejects_entire_plan_before_any_repair(self):
        directory = self.repo / 'source';directory.mkdir();(directory / 'file').write_text('retained')
        self.stage();outside = Path(self.temp.name) / 'moved';directory.rename(outside);directory.symlink_to(outside, target_is_directory=True)
        self.repo.chmod(0o777)
        with self.assertRaises(ValueError):permissions.plan(self.repo)
        self.assertEqual(self.repo.stat().st_mode & 0o777, 0o777)

    def test_encrypted_symlink_and_foreign_owner_are_rejected(self):
        (self.repo / '.gitattributes').write_text('*.env.secret filter=git-crypt\n')
        target = Path(self.temp.name) / 'outside';target.write_text('retained')
        (self.repo / 'app.env.secret').symlink_to(target);self.stage()
        with self.assertRaises(ValueError):permissions.plan(self.repo)
        with patch.object(permissions.os, 'geteuid', return_value=os.geteuid()+1):
            with self.assertRaises(ValueError):permissions.plan(self.repo)


if __name__ == '__main__':
    unittest.main()
