"""Replay availability scenarios through the provisioned Transmission thresholds.

This small evaluator supports the aggregate InfluxQL queries used by these rules;
live datasource validation separately checks their actual InfluxQL execution.
"""
from pathlib import Path
import re
import statistics
import unittest

import yaml


CONFIG = yaml.safe_load((Path(__file__).parent / 'provisioning/alerting/transmission-alert-rules.yaml').read_text())
RULES = {rule['uid']: rule for group in CONFIG['groups'] for rule in group['rules']}


def fires_at(uid, samples, until=1200):
    rule = RULES[uid]
    stages = {stage['refId']: stage for stage in rule['data']}
    query = stages['A']['model']['query']
    match = re.fullmatch(
        r'SELECT (mean|min|count)\("(\w+)"\) FROM "\w+" WHERE \$timeFilter'
        r'(?: AND "rpc_up" = 1| AND "observer" = \'native_linux\')?', query)
    if not match:
        raise ValueError('Unsupported query: ' + query)
    aggregate, field = match.groups()
    window = stages['A']['relativeTimeRange']['from']
    threshold = stages['C']['model']['conditions'][0]['evaluator']
    assert stages['B']['model']['reducer'] == 'last'
    assert rule['condition'] == 'C'
    pending = int(rule['for'].removesuffix('m')) * 60
    pending_since = None
    firing = []
    for now in range(0, until + 1, 60):
        rows = [row for timestamp, row in samples if now - window < timestamp <= now]
        if 'AND "rpc_up" = 1' in query:
            rows = [row for row in rows if row.get('rpc_up') == 1]
        if 'AND "observer"' in query:
            rows = [row for row in rows if row.get('observer') == 'native_linux']
        values = [row[field] for row in rows if field in row]
        if not values:
            breached = rule['noDataState'] == 'Alerting'
        else:
            value = {'mean': statistics.mean, 'min': min, 'count': len}[aggregate](values)
            limit = threshold['params'][0]
            breached = value < limit if threshold['type'] == 'lt' else value > limit
        if not breached:
            pending_since = None
        elif pending_since is None:
            pending_since = now
        if pending_since is not None and now - pending_since >= pending:
            firing.append(now)
    return firing


def samples(field, value_at, interval=5, until=1200, **extra):
    return [(t, {field: value_at(t), **extra}) for t in range(0, until + 1, interval)]


class TransmissionAlerts(unittest.TestCase):
    def test_observed_intermittent_endpoint_timeouts_do_not_page(self):
        # 1:00-1:15 PM Eastern on 2026-11-15: 30-second probe outcomes.
        incident = [0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 4, 4, 4, 0, 0, 4,
                    0, 0, 0, 0, 4, 4, 4, 4, 0, 0, 0, 0, 0, 0, 0, 4]
        rows = samples('result_code', lambda t: incident[(t // 30) % len(incident)], interval=30)
        self.assertEqual(fires_at('transmission_endpoint_failed', rows), [])

    def test_recoverable_rpc_stalls_do_not_page(self):
        # Even 7 of 12 short-deadline misses each minute must not imply an outage.
        rows = samples('rpc_up', lambda t: int((t // 5) % 12 >= 7), observer='native_linux')
        self.assertEqual(fires_at('transmission_host_rpc_failed', rows), [])
        rows = samples('inventory_up', lambda t: int((t // 30) % 2 == 0), interval=30, rpc_up=1)
        self.assertEqual(fires_at('transmission_inventory_failed', rows), [])

    def test_sustained_outages_still_page(self):
        for uid, field, healthy, failed, interval, extra in [
            ('transmission_endpoint_failed', 'result_code', 0, 4, 30, {}),
            ('transmission_host_rpc_failed', 'rpc_up', 1, 0, 5, {'observer': 'native_linux'}),
            ('transmission_inventory_failed', 'inventory_up', 1, 0, 30, {'rpc_up': 1}),
        ]:
            with self.subTest(uid=uid):
                rows = samples(field, lambda t: healthy if t < 300 else failed, interval=interval, **extra)
                fired = fires_at(uid, rows)
                self.assertTrue(fired)
                self.assertGreaterEqual(fired[0], 300 + 8 * 60)
                self.assertLessEqual(fired[0], 300 + 10 * 60)

    def test_near_total_rpc_failure_is_actionable(self):
        rows = samples('rpc_up', lambda t: int((t // 5) % 20 == 0), observer='native_linux')
        self.assertTrue(fires_at('transmission_host_rpc_failed', rows))

    def test_short_total_outage_recovers_before_paging(self):
        rows = samples('result_code', lambda t: 4 if 300 <= t < 480 else 0, interval=30)
        self.assertEqual(fires_at('transmission_endpoint_failed', rows), [])

    def test_mixed_persistent_endpoint_errors_are_actionable(self):
        rows = samples('result_code', lambda t: 1 + (t // 30) % 4, interval=30)
        self.assertTrue(fires_at('transmission_endpoint_failed', rows))

    def test_missing_collection_is_a_telemetry_alert(self):
        for uid in ['transmission_endpoint_failed', 'transmission_host_rpc_failed', 'transmission_inventory_failed']:
            self.assertEqual(fires_at(uid, []), [])
        for uid in ['transmission_telemetry_missing', 'transmission_host_rpc_missing']:
            self.assertTrue(fires_at(uid, []))


if __name__ == '__main__':
    unittest.main()
