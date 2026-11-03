import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('media_mount', Path(__file__).with_name('check-media-mount.py'))
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


def record(target='/srv/Media', source='nas.example:/Media', fstype='nfs4', access='rw', options='hard,vers=4.1,proto=tcp'):
    return f'25 20 0:50 / {target} {access},relatime - {fstype} {source} {access},{options}\n'


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.policy = guard.Policy.load({'mountpoint':'/srv/Media', 'source':'nas.example:/Media', 'access':'rw', 'required_roots':['data']})

    def test_absent_and_wrong_mounts_never_probe_or_create_local_roots(self):
        for info in ('', record(target='/srv'), record(source='other:/Media'), record(fstype='ext4')):
            with self.subTest(info=info), patch.object(guard, 'probe_roots') as probe:
                with self.assertRaises(guard.AdmissionError): guard.check(self.policy, info)
                probe.assert_not_called()

    def test_access_soft_options_and_protocol_fail_closed(self):
        for info in (record(access='ro'), record(options='soft,vers=4.1,proto=tcp'), record(options='hard,softreval,vers=4.1,proto=tcp'), record(options='hard,vers=3,proto=tcp'), record(options='hard,vers=4.1,proto=udp')):
            with self.subTest(info=info), self.assertRaises(guard.AdmissionError):
                guard.validate_mount(self.policy, guard.parse_mountinfo(info))

    def test_rejects_shadow_submount_and_duplicate_mount(self):
        for info in (record()+record(target='/srv/Media/data', source='other:/tree'), record()+record()):
            with self.assertRaises(guard.AdmissionError): guard.validate_mount(self.policy, guard.parse_mountinfo(info))

    def test_valid_mount_and_escaped_kernel_target(self):
        policy = guard.Policy.load({'mountpoint':'/srv/Media Files', 'source':'nas.example:/Media', 'access':'rw', 'required_roots':['data']})
        self.assertEqual(guard.validate_mount(policy, guard.parse_mountinfo(record(target=r'/srv/Media\040Files'))).target, '/srv/Media Files')

    def test_unrelated_wsl_super_options_can_contain_spaces(self):
        info = record() + r'30 20 0:51 / /Docker/host rw - 9p C:\134Program\040Files rw,path=C:\Program Files\Docker' + '\n'
        self.assertEqual(guard.validate_mount(self.policy, guard.parse_mountinfo(info)).source, self.policy.source)

    def test_invalid_policy_and_mountinfo(self):
        for roots in ([], ['../other'], ['/data'], ['data/../other'], ['data//movies'], ['link\\outside']):
            with self.subTest(roots=roots), self.assertRaises(guard.AdmissionError): guard.Policy.load({'mountpoint':'/srv/Media','source':'nas:/Media','access':'rw','required_roots':roots})
        with self.assertRaises(guard.AdmissionError): guard.parse_mountinfo('malformed')

    def test_missing_directory_and_symlink_do_not_admit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            policy=guard.Policy(str(root), 'nas:/Media', 'rw', ('data',))
            with self.assertRaises(FileNotFoundError): guard.probe_roots(policy)
            self.assertFalse((root/'data').exists())
            (root/'outside').mkdir(); (root/'data').symlink_to(root/'outside', target_is_directory=True)
            with self.assertRaises(guard.AdmissionError): guard.probe_roots(policy)
            (root/'data').unlink(); (root/'data').mkdir()
            guard.probe_roots(policy)


if __name__ == '__main__': unittest.main()
