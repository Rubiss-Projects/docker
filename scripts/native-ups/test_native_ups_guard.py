import unittest
from native_ups_guard import advance, decision


class PowerDecisionTests(unittest.TestCase):
    def test_admitted_policy_cases(self):
        cases = [('OL', 0, 'online'), ('OL CHRG', 50, 'online'),
                 ('OB', 0, 'battery-wait'), ('OB', 29, 'battery-wait'),
                 ('OB', 30, 'sustained-battery'), ('OB LB', 0, 'critical'),
                 ('FSD', 0, 'critical'), ('OFF', 0, 'critical'),
                 ('OL OB', 0, 'unknown'), ('OL ALARM', 0, 'unknown'),
                 ('INVALID', 0, 'unknown'), (None, 0, 'unknown')]
        for flags, elapsed, expected in cases:
            with self.subTest(flags=flags, elapsed=elapsed):
                self.assertEqual(decision(flags, elapsed), expected)

    def test_known_battery_deadline_survives_lost_or_invalid_status(self):
        self.assertEqual(advance('OB', None, 100), ('battery-wait', 100))
        self.assertEqual(advance(None, 100, 129), ('unknown', 100))
        self.assertEqual(advance(None, 100, 130), ('battery-status-lost', 100))
        self.assertEqual(advance('INVALID', 100, 130), ('battery-status-lost', 100))

    def test_communication_loss_alone_never_admits_shutdown(self):
        self.assertEqual(advance(None, None, 999), ('unknown', None))

    def test_confirmed_utility_return_clears_deadline(self):
        self.assertEqual(advance('OL', 100, 131), ('online', None))


if __name__ == '__main__':
    unittest.main()
