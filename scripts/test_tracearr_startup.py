"""Regression checks for Tracearr deployment and Windows maintenance ordering."""

import importlib.util
from pathlib import Path
import subprocess
import unittest
import tempfile
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installer', SCRIPTS / 'install-tracearr-maintenance.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class StartupOrderTests(unittest.TestCase):
    original = '''# header
$DockerWslBindRepairOrder = @(
    "socket-proxy",
    "uptime-kuma",
    "plex",
    "swag",
    "bitwarden"
)
# untouched footer
'''

    def test_maintenance_priority_and_idempotence(self):
        updated = installer.update_order(self.original)
        self.assertEqual(updated.replace('    "tracearr",\n', ''), self.original)
        self.assertIn('    "swag",\n    "tracearr",\n    "bitwarden"', updated)
        self.assertEqual(installer.update_order(updated), updated)

    def test_unknown_or_conflicting_order_fails_closed(self):
        for text in [self.original.replace('"plex"', '"other"'),
                     self.original.replace('"bitwarden"', '"tracearr",\n    "tracearr"'),
                     self.original + self.original]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                installer.update_order(text)

    def test_deploy_dependencies_and_priority(self):
        # Load definitions only, never run the deployment entry point.
        script = (SCRIPTS / 'deploy-changed-service-folders.sh').read_text()
        self.assertTrue(script.endswith('main "$@"\n'))
        definitions = script.rsplit('main "$@"', 1)[0]
        result = subprocess.check_output(['bash'], input=definitions + '''
stack_dependencies tracearr
order_service_dirs sonarr tracearr swag plex uptime-kuma socket-proxy
''', text=True)
        self.assertEqual(result.splitlines(), ['plex', 'socket-proxy', 'uptime-kuma', 'plex', 'swag', 'tracearr', 'sonarr'])

    def test_atomic_replace_preserves_old_file_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'helper.ps1'
            path.write_text('old complete helper')
            def reject_replace(source, target):
                self.assertEqual(path.read_text(), 'old complete helper')
                self.assertEqual(Path(source).read_text(), 'new complete helper')
                self.assertEqual(Path(source).parent, path.parent)
                raise PermissionError('concurrent Windows reader')
            with patch.object(installer.os, 'replace', side_effect=reject_replace):
                with self.assertRaises(PermissionError):
                    installer.atomic_write(path, 'new complete helper')
            self.assertEqual(path.read_text(), 'old complete helper')
            self.assertEqual(list(path.parent.iterdir()), [path])
            installer.atomic_write(path, 'new complete helper')
            self.assertEqual(path.read_text(), 'new complete helper')

    def test_retired_service_sentinel_replaced_and_idempotent(self):
        original = """#!/usr/bin/env bash
if is_running tautulli; then
  check tautulli docker exec tautulli sh -lc 'test $(stat -c%s /config/tautulli.db) -gt 1000000 && test -f /config/config.ini'
fi
# other checks unchanged
"""
        updated = installer.update_sentinel(original)
        self.assertNotIn('tautulli', updated)
        self.assertIn('check tracearr-history', updated)
        self.assertIn('x.mode === "ready" && x.db && x.redis', updated)
        self.assertTrue(updated.endswith('# other checks unchanged\n'))
        self.assertEqual(installer.update_sentinel(updated), updated)
        subprocess.run(['bash', '-n'], input=updated, text=True, check=True)
        with self.assertRaises(ValueError):
            installer.update_sentinel(original.replace('1000000', '2000000'))


if __name__ == '__main__':
    unittest.main()
