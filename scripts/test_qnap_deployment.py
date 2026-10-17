"""Exercise config-only deployment and readiness failures without live Docker."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('deploy-changed-service-folders.sh')


class QnapDeploymentTests(unittest.TestCase):
    def deploy(self, stack, *, invalid_config=False, unhealthy=False,
               dry_run=False, reload_state='success'):
        source = SCRIPT.read_text()
        self.assertTrue(source.endswith('main "$@"\n'))
        definitions = source.rsplit('main "$@"', 1)[0]
        mocks = r'''
compose() {
  printf 'compose %s\n' "$*"
}
docker() {
  printf 'docker %s\n' "$*" >&2
  if [[ "$*" == 'exec prometheus promtool check config /etc/prometheus/prometheus.yml' && "$TEST_INVALID" == 1 ]]; then
    return 23
  fi
  if [[ "$*" == 'exec prometheus /bin/sh -c kill -HUP 1' ]]; then
    touch reloaded
  fi
  if [[ "$*" == 'exec prometheus wget '* ]]; then
    if [[ ! -f reloaded || "$TEST_RELOAD_STATE" == stale ]]; then
      printf '%s\n' '{"status":"success","data":{"reloadConfigSuccess":true,"lastConfigTime":"2026-10-17T00:00:00Z"}}'
    elif [[ "$TEST_RELOAD_STATE" == failed ]]; then
      printf '%s\n' '{"status":"success","data":{"reloadConfigSuccess":false,"lastConfigTime":"2026-10-17T00:00:00Z"}}'
    else
      printf '%s\n' '{"status":"success","data":{"reloadConfigSuccess":true,"lastConfigTime":"2026-10-17T00:01:00Z"}}'
    fi
  fi
}
sleep() { SECONDS=$((SECONDS + 30)); }
verify_config_mounts() { :; }
verify_stack_readiness() {
  printf 'ready %s\n' "$1"
  [[ "$TEST_UNHEALTHY" == 0 ]]
}
wait_container_url() { printf 'probe %s\n' "$*"; }
DRY_RUN=$TEST_DRY_RUN
deploy_stack "$TEST_STACK"
'''
        with tempfile.TemporaryDirectory() as root:
            Path(root, stack).mkdir()
            env = dict(os.environ, DOCKER_REPO_DIR=root, DOCKER_DEPLOY_SCOPE='main',
                       TEST_STACK=stack, TEST_INVALID=str(int(invalid_config)),
                       TEST_UNHEALTHY=str(int(unhealthy)),
                       TEST_RELOAD_STATE=reload_state,
                       TEST_DRY_RUN=str(dry_run).lower())
            return subprocess.run(['bash'], input=definitions + mocks, env=env,
                                  text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT)

    def test_unchanged_prometheus_container_gets_validated_then_reloaded(self):
        result = self.deploy('prometheus')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertLess(result.stdout.index('promtool check config'),
                        result.stdout.index('kill -HUP 1'))
        self.assertNotIn('docker kill', result.stdout)
        self.assertIn('confirmed Prometheus configuration reload', result.stdout)

    def test_invalid_config_stops_before_hup(self):
        result = self.deploy('prometheus', invalid_config=True)
        self.assertEqual(result.returncode, 23)
        self.assertNotIn('kill -HUP', result.stdout)

    def test_unsuccessful_or_stale_reload_does_not_report_success(self):
        for state in ('failed', 'stale'):
            with self.subTest(state=state):
                result = self.deploy('prometheus', reload_state=state)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('did not confirm', result.stdout)
                self.assertNotIn('confirmed Prometheus configuration reload', result.stdout)

    def test_healthy_exporter_syncs_monitor_without_restarting_swag(self):
        result = self.deploy('snmp-exporter')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertLess(result.stdout.index('ready snmp-exporter'),
                        result.stdout.index('docker exec swag python3 /app/auto-uptime-kuma.py'))
        self.assertNotIn('restart', result.stdout)

    def test_unhealthy_exporter_does_not_sync_monitor(self):
        result = self.deploy('snmp-exporter', unhealthy=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('auto-uptime-kuma.py', result.stdout)

    def test_dry_run_does_not_apply_configuration(self):
        for stack in ('prometheus', 'snmp-exporter'):
            with self.subTest(stack=stack):
                result = self.deploy(stack, dry_run=True)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('docker exec', result.stdout)


if __name__ == '__main__':
    unittest.main()
