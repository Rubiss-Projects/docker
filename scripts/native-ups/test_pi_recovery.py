import unittest

from pi_recovery import transition


class RecoveryPolicyTests(unittest.TestCase):
    def outage(self):
        state = {}
        transition(state, 'OL', 100, {'ben-server'}, 0)
        transition(state, 'OB', 99, {'ben-server'}, 5)
        return state

    def test_only_previously_running_hosts_wake_after_stable_power(self):
        state = self.outage()
        self.assertEqual(transition(state, 'OL', 90, set(), 50), [])
        self.assertEqual(transition(state, 'OL', 90, set(), 229), [])
        self.assertEqual(transition(state, 'OL', 90, set(), 230), ['ben-server'])
        self.assertNotIn('ben-pc', state['pending'])

    def test_return_during_committed_shutdown_keeps_candidate(self):
        state = self.outage()
        transition(state, 'OL', 90, {'ben-server'}, 40)
        self.assertIn('ben-server', state['pending'])
        self.assertEqual(transition(state, 'OL', 90, set(), 220), ['ben-server'])

    def test_brief_outage_clears_running_candidate(self):
        state = self.outage()
        transition(state, 'OL', 90, {'ben-server'}, 10)
        self.assertEqual(transition(state, 'OL', 90, {'ben-server'}, 190), [])
        self.assertEqual(state['pending'], {})

    def test_unknown_or_low_charge_never_wakes(self):
        state = self.outage()
        transition(state, 'OL', 10, set(), 20)
        self.assertEqual(transition(state, 'OL', 10, set(), 200), [])
        self.assertEqual(transition(state, None, 100, set(), 205), [])
        self.assertEqual(transition(state, 'OL', 100, set(), 210), [])
        self.assertEqual(transition(state, 'OL', 100, set(), 390), ['ben-server'])

    def test_retry_limit_and_interval(self):
        state = self.outage()
        transition(state, 'OL', 100, set(), 10)
        row = state['pending']['ben-server']
        row.update(attempts=1, lastAttempt=180)
        self.assertEqual(transition(state, 'OL', 100, set(), 200), [])
        self.assertEqual(transition(state, 'OL', 100, set(), 240), ['ben-server'])
        row['attempts'] = 5
        self.assertEqual(transition(state, 'OL', 100, set(), 500), [])

    def test_no_outage_no_wake_and_no_stale_inventory(self):
        state = {}
        transition(state, 'OL', 100, {'ben-pc'}, 0)
        self.assertEqual(transition(state, None, 100, set(), 30), [])
        transition(state, 'OB', 90, set(), 40)
        transition(state, 'OL', 100, set(), 60)
        self.assertEqual(transition(state, 'OL', 100, set(), 240), [])


if __name__ == '__main__':
    unittest.main()
