import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('native_installer', Path(__file__).parents[1] / 'install-telegraf-native.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class NativeInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config_dir = self.root / 'telegraf.d'
        self.config_dir.mkdir()
        self.lib = self.root / 'lib'
        self.config = self.root / 'telegraf.conf'
        self.base_config = '[[outputs.influxdb_v2]]\nurls=["http://127.0.0.1:8086"]\ntoken="private-test-token"\n[[inputs.cpu]]\n[[inputs.mem]]\n[[inputs.disk]]\n[[inputs.system]]\n'
        self.config.write_text(self.base_config)
        self.credentials = self.root / 'credentials.json'
        self.credentials.write_text(json.dumps({'USER': '', 'PASS': ''}))
        self.credentials.chmod(0o600)
        self.events = []
        self.validation_fails = False
        self.restart_times_out = False
        self.patch = patch.multiple(installer, CONFIG=self.config, CONFIG_DIR=self.config_dir, CREDENTIALS=self.credentials, LIB=self.lib, BACKUP_ROOT=self.root / 'backups')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        for target, value in [('geteuid', lambda: 0)]:
            p = patch.object(installer.os, target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(installer.pwd, 'getpwnam', return_value=SimpleNamespace(pw_gid=os.getgid()))
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(installer.shutil, 'which', return_value='/usr/bin/telegraf')
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(installer.subprocess, 'check_output', return_value='/usr/bin/telegraf -config /etc/telegraf/telegraf.conf -config-directory /etc/telegraf/telegraf.d')
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(installer.subprocess, 'run', side_effect=self.command)
        p.start()
        self.addCleanup(p.stop)

    def command(self, args, **kwargs):
        self.events.append(args)
        if self.restart_times_out and args[:2] == ['systemctl', 'restart']:
            raise subprocess.TimeoutExpired(args, 30)
        is_validation = args[0] == 'runuser'
        return SimpleNamespace(returncode=1 if is_validation and self.validation_fails else 0, stdout=b'transmission_host_rpc,rpc_up=1i\ntransmission,rpc_up=1\n', stderr=b'')

    def run_installer(self, apply=True):
        with patch.object(installer.sys, 'argv', ['installer', *(['--apply'] if apply else [])]), contextlib.redirect_stdout(io.StringIO()) as output:
            installer.main()
        return output.getvalue()

    @unittest.skipUnless(os.getuid() == 0, 'Uses genuine root-owned disposable files')
    def test_dry_run_never_installs_or_restarts(self):
        self.run_installer(apply=False)
        self.assertFalse(self.lib.exists())
        self.assertEqual(self.config.read_text(), self.base_config)
        self.assertFalse(any('restart' in event for event in self.events))

    @unittest.skipUnless(os.getuid() == 0, 'Uses genuine root-owned disposable files')
    def test_install_preserves_output_and_second_apply_is_a_noop(self):
        output = self.run_installer()
        self.assertNotIn('private-test-token', output)
        self.assertEqual(self.config.read_text(), self.base_config)
        self.assertTrue((self.config_dir / 'transmission-native.conf').exists())
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o640)
        self.assertEqual(sum('restart' in event for event in self.events), 1)
        self.events.clear()
        self.run_installer()
        self.assertFalse(any('restart' in event or event[0] == 'runuser' for event in self.events))

    @unittest.skipUnless(os.getuid() == 0, 'Uses genuine root-owned disposable files')
    def test_invalid_candidate_restores_previous_files_without_restarting_collector(self):
        self.lib.mkdir()
        previous = self.lib / 'native-host-rpc.py'
        previous.write_bytes(b'previous-probe')
        previous.chmod(0o755)
        self.validation_fails = True
        with self.assertRaises(AssertionError):
            self.run_installer()
        self.assertEqual(previous.read_bytes(), b'previous-probe')
        self.assertFalse((self.lib / 'rpc-health.py').exists())
        self.assertFalse((self.config_dir / 'transmission-native.conf').exists())
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.read_text(), self.base_config)
        self.assertFalse(any('restart' in event for event in self.events))

    @unittest.skipUnless(os.getuid() == 0, 'Uses genuine root-owned disposable files')
    def test_first_install_under_private_umask_keeps_probe_directories_accessible(self):
        self.config_dir.rmdir()
        previous_umask = os.umask(0o077)
        try:
            self.run_installer()
        finally:
            os.umask(previous_umask)
        for directory in [self.lib, self.config_dir]:
            self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.config.read_text(), self.base_config)

    @unittest.skipUnless(os.getuid() == 0, 'Uses genuine root-owned disposable files')
    def test_restart_observation_timeout_never_starts_a_competing_job(self):
        self.restart_times_out = True
        with self.assertRaisesRegex(RuntimeError, 'Observe the existing'):
            self.run_installer()
        self.assertTrue((self.config_dir / 'transmission-native.conf').exists())
        self.assertEqual(sum('restart' in event for event in self.events), 1)

    @unittest.skipUnless(os.getuid() == 0, 'Uses genuine root-owned disposable files')
    def test_unmanaged_duplicate_probe_is_rejected_before_any_write(self):
        self.config.write_text(self.base_config + '\n[[inputs.exec]]\ncommands=["python3 /some/transmission-probe.py"]\n')
        with self.assertRaisesRegex(AssertionError, 'existing Transmission inputs'):
            self.run_installer()
        self.assertFalse(self.lib.exists())
        self.assertFalse(any('restart' in event for event in self.events))
