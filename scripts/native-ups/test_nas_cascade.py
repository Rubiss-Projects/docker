import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import nas_cascade as nas
from pi_recovery import transition

BOOT = '12345678-1234-1234-1234-123456789abc'


class CascadeTests(unittest.TestCase):
    def outage(self):
        state = {}
        status = {'boot': BOOT, 'ready': True}
        nas.cascade(state, 'OL', {'nas', 'ben-server'}, status, None, 100)
        nas.cascade(state, 'OB', {'nas', 'ben-server'}, status, None, 105)
        return state, status

    def release(self, state):
        return {'event': state['cascade']['id'], 'phase': 'released'}

    def test_immediate_after_release_and_server_offline(self):
        state, status = self.outage()
        receipt = self.release(state)
        self.assertIsNone(nas.cascade(state, 'OB', {'ben-server'}, status, receipt, 136))
        self.assertEqual(nas.cascade(state, 'OB', set(), status, receipt, 137),
                         'server-storage-released')

    def test_ping_loss_alone_does_not_admit_early_shutdown(self):
        state, status = self.outage()
        self.assertIsNone(nas.cascade(state, 'OB', set(), status, None, 136))
        self.assertIsNone(nas.cascade(state, None, set(), status, None, 1000))
        self.assertEqual(nas.cascade(state, 'OB', set(), status, None, 285),
                         'server-drain-timeout')

    def test_critical_battery_does_not_wait_for_server(self):
        state, status = self.outage()
        self.assertEqual(nas.cascade(state, 'OB LB', {'ben-server'}, status, None, 106),
                         'critical-battery')

    def test_stale_release_and_new_nas_boot_cannot_shutdown(self):
        state, status = self.outage()
        stale = {'event': str(uuid.uuid4()), 'phase': 'released'}
        self.assertIsNone(nas.cascade(state, 'OB', set(), status, stale, 136))
        status['boot'] = str(uuid.uuid4())
        self.assertIsNone(nas.cascade(state, 'OB LB', set(), status, self.release(state), 300))

    def test_return_during_committed_shutdown_finishes_cascade(self):
        state, status = self.outage()
        self.assertEqual(nas.cascade(state, 'OL', set(), status, self.release(state), 140),
                         'server-storage-released')

    def test_short_outage_does_not_inherit_old_failure_deadline(self):
        state, status = self.outage()
        old = state['cascade']['id']
        nas.cascade(state, 'OL', {'nas', 'ben-server'}, status, None, 110)
        self.assertIsNone(nas.cascade(state, 'OB', set(), status, None, 120))
        self.assertNotEqual(old, state['cascade']['id'])
        self.assertEqual(state['cascade']['started'], 120)

    def test_requested_action_is_not_repeated_after_restart(self):
        state, status = self.outage()
        state['cascade']['requested'] = True
        restored = json.loads(json.dumps(state))
        self.assertIsNone(nas.cascade(restored, 'OB LB', set(), status, self.release(state), 300))

    def test_abandoned_handshake_expires_after_power_returns(self):
        state, status = self.outage()
        receipt = {'event': state['cascade']['id'], 'phase': 'begin'}
        nas.cascade(state, 'OL', {'nas', 'ben-server'}, status, receipt, 110)
        nas.cascade(state, 'OL', {'nas', 'ben-server'}, status, receipt, 290)
        self.assertNotIn('cascade', state)
        self.assertIsNone(nas.cascade(state, 'OB', {'nas'}, status, receipt, 295))
        self.assertEqual(state['cascade']['started'], 295)

    def test_only_recorded_nas_can_be_shutdown(self):
        self.assertIsNone(nas.cascade({}, 'OB LB', set(), None, None, 100))

    def test_server_wake_waits_for_storage_readiness(self):
        state = {}
        transition(state, 'OL', 100, {'nas', 'ben-server', 'ben-pc'}, 0)
        transition(state, 'OB', 90, set(), 5)
        transition(state, 'OL', 90, set(), 40)
        self.assertEqual(set(transition(state, 'OL', 90, set(), 220)), {'nas', 'ben-pc'})
        self.assertNotIn('ben-server', transition(state, 'OL', 90, {'nas'}, 225))
        self.assertIn('ben-server', transition(state, 'OL', 90, {'nas'}, 230, nas_ready=True))

    def test_receiver_binds_release_to_event_and_boot(self):
        state, _ = self.outage()
        with tempfile.TemporaryDirectory() as folder, patch.object(nas, 'ROOT', Path(folder)), \
                patch.object(nas.os, 'geteuid', return_value=0):
            (Path(folder) / 'state.json').write_text(json.dumps(state))
            with patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': f'begin {BOOT}'}):
                nas.receive()
            with patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': f'released {BOOT} {uuid.uuid4()}'}):
                with self.assertRaises(ValueError):
                    nas.receive()
            with patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': f'released {BOOT} {state["cascade"]["id"]}'}):
                nas.receive()
            self.assertEqual(json.loads((Path(folder) / 'server-release.json').read_text())['phase'],
                             'released')


if __name__ == '__main__':
    unittest.main()
