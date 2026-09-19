"""Regression check for Tracearr deployment ordering."""

from pathlib import Path
import subprocess
import unittest

SCRIPTS = Path(__file__).resolve().parent


class StartupOrderTests(unittest.TestCase):
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
