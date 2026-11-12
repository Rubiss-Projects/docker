import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import server_storage_release as release


class StorageReleaseTests(unittest.TestCase):
    def test_no_shutdown_without_current_boot_intent(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(release, 'ROOT', Path(folder)), \
                patch.object(release.os, 'geteuid', return_value=0), \
                patch.object(release.socket, 'gethostname', return_value='ben-server'), \
                patch.object(release, 'run') as run:
            (Path(folder) / 'shutdown-intent.json').write_text(json.dumps(
                {'boot': 'old', 'decision': 'sustained-battery'}))
            with self.assertRaisesRegex(ValueError, 'current UPS'):
                release.main()
            run.assert_not_called()

    def test_unmount_failure_never_reports_release_but_still_powers_off(self):
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        calls = []

        def command(args, timeout):
            calls.append(args)
            if 'begin ' in args[-1]:
                return Mock(stdout='12345678-1234-1234-1234-123456789abc')
            if 'srv-Media.mount' in args:
                raise OSError('busy mount')
            return Mock(stdout='')

        with tempfile.TemporaryDirectory() as folder, patch.object(release, 'ROOT', Path(folder)), \
                patch.object(release.os, 'geteuid', return_value=0), \
                patch.object(release.socket, 'gethostname', return_value='ben-server'), \
                patch.object(release, 'run', side_effect=command), \
                patch.object(release.Path, 'mkdir'), patch.object(release.Path, 'write_text'):
            # Write through open because write_text is mocked for the /run drop-in.
            with (Path(folder) / 'shutdown-intent.json').open('w') as stream:
                json.dump({'boot': boot, 'decision': 'sustained-battery'}, stream)
            release.main()
        self.assertFalse(any(args[-1].startswith('released ') for args in calls))
        self.assertEqual(calls[-1], ['systemctl', '--no-block', 'poweroff'])


if __name__ == '__main__':
    unittest.main()
