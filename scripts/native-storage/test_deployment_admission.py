import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deployment', Path(__file__).with_name('check-deployment-admission.py'))
admission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admission)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'schemaVersion': 1, 'state': 'preparation_only', 'automaticStartAllowed': False,
                     'stacks': [{'stack': 'plex', 'compose': 'plex/docker-compose.yml', 'services': ['plex'], 'disposition': 'keep'},
                                {'stack': 'old', 'compose': 'old/compose.yaml', 'services': ['old'], 'disposition': 'archive'}]}
        self.policy = {'schemaVersion': 1, 'nativeAcceptanceCompleted': True,
                       'startupPlanSha256': admission.plan_digest(self.plan), 'releasedStacks': ['plex'],
                       'allowedMaintenanceInstallers': {}}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / 'plex').mkdir()
        (self.repo / 'plex/docker-compose.yml').write_text('services: {plex: {image: fixture}}\n')
        (self.repo / 'scripts/native-storage/overrides').mkdir(parents=True)
        (self.repo / 'scripts/native-storage/overrides/plex.yaml').write_text('services: {plex: {}}\n')

    def test_keep_is_not_authorization_and_default_policy_denies(self):
        rows = admission.validate_release(self.plan, self.policy)
        self.assertEqual(admission.require_stack(rows, self.policy, 'plex')['stack'], 'plex')
        for value in (False, 'true', 1):
            p = {**self.policy, 'nativeAcceptanceCompleted': value}
            with self.assertRaises(ValueError):
                admission.validate_release(self.plan, p)
        with self.assertRaises(ValueError):
            admission.require_stack(rows, {**self.policy, 'releasedStacks': []}, 'plex')

    def test_shipped_example_never_releases_a_stack_or_installer(self):
        example = admission.load_json(Path(__file__).with_name('native-deployment-policy.example.json').read_bytes())
        self.assertIs(example['nativeAcceptanceCompleted'], False)
        self.assertEqual(example['releasedStacks'], [])
        self.assertEqual(example['allowedMaintenanceInstallers'], {})
        with self.assertRaises(ValueError):
            admission.validate_release(self.plan, example)

    def test_all_non_keep_dispositions_and_unknown_or_duplicate_release_are_held(self):
        for disposition in ('archive', 'defer', 'replace', 'omit'):
            plan = copy.deepcopy(self.plan)
            plan['stacks'][1]['disposition'] = disposition
            policy = {**self.policy, 'startupPlanSha256': admission.plan_digest(plan), 'releasedStacks': ['old']}
            with self.assertRaises(ValueError):
                admission.validate_release(plan, policy)
        for names in (['unknown'], ['pi/plex'], ['plex', 'plex']):
            with self.assertRaises(ValueError):
                admission.validate_release(self.plan, {**self.policy, 'releasedStacks': names})

    def test_private_release_binds_semantics_not_json_line_endings(self):
        equivalent = json.loads(json.dumps(self.plan, indent=2).replace('\n', '\r\n'))
        self.assertEqual(admission.plan_digest(self.plan), admission.plan_digest(equivalent))
        changed = copy.deepcopy(self.plan)
        changed['stacks'][0]['services'].append('new')
        with self.assertRaises(ValueError):
            admission.validate_release(changed, self.policy)
        with self.assertRaises(ValueError):
            admission.validate_release(self.plan, {**self.policy, 'extra': True})

    def test_duplicate_json_keys_and_invalid_stack_or_compose_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            admission.load_json('{"schemaVersion": 1, "schemaVersion": 2}')
        for name, compose in (('../plex', '../plex/compose.yml'), ('plex', 'other/compose.yml')):
            plan = copy.deepcopy(self.plan)
            plan['stacks'][0].update(stack=name, compose=compose)
            with self.assertRaises(ValueError):
                admission.reviewed_stacks(plan)

    def test_required_overlay_cannot_silently_fall_back_to_windows_base(self):
        row = self.plan['stacks'][0]
        self.assertEqual([p.relative_to(self.repo).as_posix() for p in admission.compose_files(self.repo, row)],
                         ['plex/docker-compose.yml', 'scripts/native-storage/overrides/plex.yaml'])
        (self.repo / 'scripts/native-storage/overrides/plex.yaml').unlink()
        with self.assertRaises(ValueError):
            admission.compose_files(self.repo, row)

    def test_compiled_services_must_match_before_deployment(self):
        row = self.plan['stacks'][0]
        (self.repo / 'plex/.env.secret').write_text('FIXTURE=not-a-secret\n')
        with patch.object(admission.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'plex\n', '')) as run:
            admission.check_services(self.repo, row)
            argv = run.call_args.args[0]
            self.assertEqual(argv[:4], ['docker', 'compose', '--env-file', '.env.secret'])
            self.assertEqual(argv[-2:], ['config', '--services'])
            self.assertEqual(argv.count('--file'), 2)
            self.assertNotIn('up', argv)
        for result in (subprocess.CompletedProcess([], 0, 'plex\nunreviewed\n', ''),
                       subprocess.CompletedProcess([], 1, '', 'potentially sensitive renderer detail')):
            with patch.object(admission.subprocess, 'run', return_value=result):
                with self.assertRaisesRegex(ValueError, 'services differ') as error:
                    admission.check_services(self.repo, row)
                self.assertNotIn('sensitive', str(error.exception))

    def test_installer_allowlist_requires_explicit_path_and_digest(self):
        for installers in ([], {'../script.sh': 'a' * 64}, {'scripts/job.sh': 'unreviewed'}):
            with self.assertRaises(ValueError):
                admission.validate_release(self.plan, {**self.policy, 'allowedMaintenanceInstallers': installers})
        admission.validate_release(self.plan, {**self.policy, 'allowedMaintenanceInstallers': {'scripts/job.sh': 'a' * 64}})

    @unittest.skipUnless(hasattr(os, 'O_NOFOLLOW') and os.getuid() == 0, 'Linux root fixture verifies runtime file ownership')
    def test_policy_loader_rejects_writable_files_and_symlinks(self):
        policy = self.repo / 'policy.json'
        policy.write_text(json.dumps(self.policy))
        policy.chmod(0o600)
        self.assertEqual(admission.load_private_policy(policy), self.policy)
        policy.chmod(0o666)
        with self.assertRaises(ValueError):
            admission.load_private_policy(policy)
        policy.chmod(0o600)
        link = self.repo / 'link.json'
        link.symlink_to(policy)
        with self.assertRaises(OSError):
            admission.load_private_policy(link)

    @unittest.skipUnless(hasattr(os, 'O_NOFOLLOW') and os.getuid() == 0, 'Linux root fixture verifies private policy admission')
    def test_installer_cli_only_checks_exact_approved_bytes_and_never_executes(self):
        script = self.repo / 'scripts/job.sh'
        marker = self.repo / 'would-have-run'
        script.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        plan = self.repo / 'scripts/native-storage/startup-plan.json'
        plan.write_text(json.dumps(self.plan))
        policy = self.repo / 'policy.json'
        policy.write_text(json.dumps({**self.policy, 'allowedMaintenanceInstallers': {
            'scripts/job.sh': hashlib.sha256(script.read_bytes()).hexdigest()}}))
        policy.chmod(0o600)
        argv = ['check', '--repo', str(self.repo), '--policy', str(policy), '--installer', 'scripts/job.sh']
        with patch.object(admission.sys, 'argv', argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(admission.main(), 0)
            script.write_text(script.read_text() + '# changed since review\n')
            self.assertEqual(admission.main(), 1)
        self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
