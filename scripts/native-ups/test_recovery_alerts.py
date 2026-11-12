import os
import unittest
from unittest.mock import Mock, patch

from recovery_alerts import notify, problems


class AlertTests(unittest.TestCase):
    def test_unknown_status_debounce_and_recovery(self):
        state = {'status': None}
        self.assertEqual(problems(state, 0), [])
        self.assertTrue(problems(state, 60))
        state['status'] = 'OL'
        self.assertEqual(problems(state, 65), [])
        self.assertNotIn('unknownSince', state)

    def test_exhausted_wake_and_storage_wait(self):
        state = {'status': 'OL', 'pending': {'ben-server': {'attempts': 5}},
                 'onlineSince': 0, 'nasReady': False}
        self.assertEqual(len(problems(state, 600)), 2)

    def test_failure_retry_is_bounded_and_success_deduplicated(self):
        state = {'status': 'OL', 'pending': {'nas': {'held': 'test'}}}
        opener = Mock()
        opener.open.side_effect = OSError('do not expose endpoint')
        with patch.dict(os.environ, {'UPS_RECOVERY_WEBHOOK': 'https://discord.com/api/webhooks/test'}), \
                patch('urllib.request.build_opener', return_value=opener):
            notify(state, 0)
            notify(state, 299)
            self.assertEqual(opener.open.call_count, 1)
            self.assertNotIn('endpoint', state['notificationError'])
            response = Mock()
            response.__enter__ = Mock(return_value=Mock(status=204))
            response.__exit__ = Mock(return_value=False)
            opener.open.side_effect = None
            opener.open.return_value = response
            notify(state, 300)
            notify(state, 601)
            self.assertEqual(opener.open.call_count, 2)
            self.assertNotIn('notificationError', state)

    def test_no_network_without_configuration(self):
        with patch.dict(os.environ, {}, clear=True), patch('urllib.request.build_opener') as build:
            notify({'pending': {'nas': {'held': 'test'}}}, 100)
            build.assert_not_called()
