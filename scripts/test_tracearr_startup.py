"""Regression checks for Tracearr deployment and Windows maintenance ordering."""

import importlib.util
from pathlib import Path
import subprocess
import unittest


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


if __name__ == '__main__':
    unittest.main()
