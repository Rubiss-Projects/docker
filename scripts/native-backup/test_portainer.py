import gzip
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import portainer


class PortainerBackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.archive = self.root/'backup.tar.gz'

    def archive_with(self, names):
        with tarfile.open(self.archive, 'w:gz') as archive:
            for name, kind in names:
                member = tarfile.TarInfo(name)
                if kind == 'file':
                    member.size = 4
                    archive.addfile(member, io.BytesIO(b'data'))
                else:
                    member.type = kind
                    member.linkname = '/etc/passwd'
                    archive.addfile(member)

    def verify(self):
        with patch.object(portainer.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 0, 'OK\n', '')) as check:
            result = portainer.inspect_archive(self.archive, Path('/verified/bbolt'))
            self.assertEqual(check.call_args.args[0][1], 'check')
            self.assertEqual(Path(check.call_args.args[0][2]).parent.parent, self.root)
            return result

    def test_vendor_absolute_paths_are_read_without_absolute_extraction(self):
        self.archive_with([('/portainer.db', 'file'), ('/certs/cert.pem', 'file')])
        result = self.verify()
        self.assertEqual(result['regularFiles'], 2)
        self.assertEqual(result['regularBytes'], 8)
        self.assertEqual(set(result['files']), {'portainer.db', 'certs/cert.pem'})
        self.assertEqual(list(self.root.iterdir()), [self.archive])

    def test_reject_traversal_links_devices_and_normalized_duplicates(self):
        for members in [
            [('../portainer.db', 'file')],
            [('/certs/../portainer.db', 'file')],
            [('/portainer.db', tarfile.SYMTYPE)],
            [('/portainer.db', tarfile.LNKTYPE)],
            [('/portainer.db', tarfile.FIFOTYPE)],
            [('/portainer.db', 'file'), ('portainer.db', 'file')],
            [('/portainer.db', 'file'), ('certs\\bad', 'file')],
        ]:
            with self.subTest(members=members):
                self.archive_with(members)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_requires_root_database(self):
        self.archive_with([('/nested/portainer.db', 'file')])
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_broken_gzip_trailer_after_tar_end(self):
        self.archive_with([('/portainer.db', 'file')])
        data = bytearray(self.archive.read_bytes())
        data[-8] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaises((gzip.BadGzipFile, tarfile.ReadError, EOFError)):
            self.verify()

    def test_failed_bbolt_check_is_not_accepted(self):
        self.archive_with([('/portainer.db', 'file')])
        with patch.object(portainer.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 1, '', 'broken')):
            with self.assertRaisesRegex(ValueError, 'consistency'):
                portainer.inspect_archive(self.archive, Path('/verified/bbolt'))

    def test_reused_capture_destination_never_repeats_api_request(self):
        destination = self.root/'existing'
        destination.mkdir()
        (destination/'intent.json').write_text(json.dumps({'requestMayHaveRun': True}))
        with patch.object(portainer, 'container_state') as inspect:
            with self.assertRaises(FileExistsError):
                portainer.capture(destination, Path('/verified/bbolt'))
            inspect.assert_not_called()

    def test_redirect_never_forwards_admin_key(self):
        with self.assertRaisesRegex(ValueError, 'redirect'):
            portainer.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://elsewhere/')

    def test_capture_preserves_supported_archive_and_records_encryption_pending(self):
        self.archive_with([('/portainer.db', 'file')])
        response = io.BytesIO(self.archive.read_bytes())
        response.status = 200
        state = {'Id': 'container-id', 'Image': 'image-id', 'RestartCount': 0,
                 'State': {'Running': True, 'StartedAt': 'unchanged'},
                 'Config': {'Labels': {'homepage.widget.key': 'private-test-key'}},
                 'NetworkSettings': {'Networks': {'proxynet': {'IPAddress': '172.18.0.2'}}}}
        destination = self.root/'capture'
        with patch.object(portainer, 'container_state', return_value=state), \
             patch.object(portainer.urllib.request.OpenerDirector, 'open', return_value=response) as request, \
             patch.object(portainer.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 0, 'OK\n', '')):
            result = portainer.capture(destination, Path('/verified/bbolt'))
            request.assert_called_once()
        self.assertTrue(result['encryptedRepositoryCapturePending'])
        self.assertEqual((destination/'backup.tar.gz').read_bytes(), self.archive.read_bytes())
        self.assertNotIn('private-test-key', (destination/'capture.json').read_text())
        self.assertFalse((destination/'backup.tar.gz.partial').exists())

    def test_api_timeout_retains_intent_and_refuses_a_repeat(self):
        state = {'Id': 'container-id', 'Image': 'image-id',
                 'Config': {'Labels': {'homepage.widget.key': 'private-test-key'}},
                 'NetworkSettings': {'Networks': {'proxynet': {'IPAddress': '172.18.0.2'}}}}
        destination = self.root/'capture'
        with patch.object(portainer, 'container_state', return_value=state), \
             patch.object(portainer.urllib.request.OpenerDirector, 'open', side_effect=TimeoutError) as request:
            with self.assertRaises(TimeoutError):
                portainer.capture(destination, Path('/verified/bbolt'))
            self.assertTrue((destination/'intent.json').exists())
            with self.assertRaises(FileExistsError):
                portainer.capture(destination, Path('/verified/bbolt'))
            request.assert_called_once()


if __name__ == '__main__':
    unittest.main()
