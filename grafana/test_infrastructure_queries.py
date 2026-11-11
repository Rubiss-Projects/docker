"""Exercise actual provisioned alert queries for absent telemetry and NAS states."""
import argparse
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    rules = {}
    for name in ['linux-alert-rules.yaml', 'nas-alert-rules.yaml']:
        data = yaml.safe_load((ROOT / 'grafana/provisioning/alerting' / name).read_text())
        rules.update({rule['uid']: rule['data'][0]['model']['expr']
                      for group in data['groups'] for rule in group['rules']})
    import json
    dashboard = json.loads((ROOT / 'grafana/dashboards/Sunday Edge/sunday-edge-dfs-compute.json').read_text())
    rules.update({'sunday_' + str(panel['id']): panel['targets'][0]['expr']
                  for panel in dashboard['panels'] if panel['id'] in [6, 7]})

    def case(name, uid, series, expected):
        return {'name': name, 'interval': '1m',
                'input_series': [{'series': labels, 'values': f'{value}+0x3'}
                                 for labels, value in series],
                'promql_expr_test': [{'expr': rules[uid], 'eval_time': '2m',
                                     'exp_samples': [{'labels': labels, 'value': value}
                                                     for labels, value in expected]}]}

    nas_up = 'up{job="qnap-snmp",instance="qnap-nas"}'
    pool = 'storagepoolStatus{job="qnap-snmp",instance="qnap-nas",storagepoolID="1"}'
    tests = [
        case('NAS scrape removed', 'nas_telemetry_missing', [], [('{}', 1)]),
        case('NAS scrape failing', 'nas_telemetry_missing', [(nas_up, 0)], [('{}', 1)]),
        case('NAS scrape healthy', 'nas_telemetry_missing', [(nas_up, 1)], [('{}', 0)]),
        case('Unknown negative NAS state is actionable', 'nas_pool_not_ready', [(pool, -4)],
             [('{job="qnap-snmp",instance="qnap-nas",storagepoolID="1"}', 4)]),
        case('NAS Ready', 'nas_pool_not_ready', [(pool, 0)],
             [('{job="qnap-snmp",instance="qnap-nas",storagepoolID="1"}', 0)]),
        case('No drive identities', 'nas_drive_identity_missing', [], [('{}', 0)]),
        case('Missing UPS recording series', 'ups_telemetry_missing', [], [('{}', 1)]),
        case('Invalid UPS status', 'ups_telemetry_missing', [('nut:telemetry_available', 0)], [('{}', 1)]),
        case('Healthy UPS', 'ups_telemetry_missing', [('nut:telemetry_available', 1)], [('{}', 0)]),
        case('Deleted native scrape job remains visible', 'linux_expected_host_missing',
             [('up{job="node-exporter-pi",instance="raspberry-pi"}', 1)],
             [('{job="node-exporter",instance="ben-server"}', 1)]),
        case('Both expected Linux scrape jobs exist', 'linux_expected_host_missing',
             [('up{job="node-exporter-pi",instance="raspberry-pi"}', 1),
              ('up{job="node-exporter",instance="ben-server"}', 1)], []),
        case('Idle healthy DFS collection shows zero throughput', 'sunday_7',
             [('up{job="sunday-edge-dfs-workers",instance="worker-1"}', 1)], [('{}', 0)]),
        case('Failed DFS collection never shows idle throughput', 'sunday_7',
             [('up{job="sunday-edge-dfs-workers",instance="worker-1"}', 0)], []),
    ]
    return {'evaluation_interval': '1m', 'tests': tests}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', help='Use promtool in an existing container without changing its server')
    args = parser.parse_args()
    if args.container:
        command = ['docker', 'exec', '-i', args.container, 'promtool', 'test', 'rules', '/dev/stdin']
    else:
        image = yaml.safe_load((ROOT / 'prometheus/docker-compose.yml').read_text())['services']['prometheus']['image']
        command = ['docker', 'run', '--rm', '-i', '--network', 'none', '--entrypoint', 'promtool',
                   image, 'test', 'rules', '/dev/stdin']
    subprocess.run(command, input=yaml.safe_dump(fixture()).encode(), check=True, timeout=120)
