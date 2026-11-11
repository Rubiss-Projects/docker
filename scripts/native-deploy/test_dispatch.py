import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'deploy-changed-service-folders.sh'


@unittest.skipIf(os.name=='nt','Native dispatch requires POSIX bash')
class DispatchTests(unittest.TestCase):
    def test_guidance_changes_do_not_admit_dormant_stacks(self):
        source=SCRIPT.read_text().rsplit('main "$@"',1)[0]
        body='''
if find_service_dir ark/CLAUDE.md; then exit 81; fi
if find_service_dir ark/AGENTS.md; then exit 82; fi
find_service_dir grafana/provisioning/alerting/nas-alert-rules.yaml || exit 83
test "$SERVICE_DIR_RESULT" = grafana || exit 84
'''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['ark','grafana']:
                (root/name).mkdir();(root/name/'docker-compose.yml').write_text('services: {}\n')
            p=subprocess.run(['bash'],input=source+body,cwd=root,text=True,capture_output=True,
                env=os.environ|{'DOCKER_REPO_DIR':str(root),'DOCKER_DEPLOY_HOST':'native-linux'})
            self.assertEqual(p.returncode,0,p.stderr)

    def test_native_checkout_creates_private_files_and_restores_umask(self):
        source=SCRIPT.read_text().rsplit('main "$@"',1)[0]
        for failed in (False,True):
            with self.subTest(failed=failed),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                body='''
git() { touch "$REPO_DIR/new-secret"; return "${SIMULATE_FAILURE}"; }
python3() { test "$1" = -B && test "$3" = --repo && test "$5" = --apply; }
umask 022
if fast_forward_checkout; then result=0; else result=$?; fi
test "$result" = "$SIMULATE_FAILURE" || exit 71
test "$(umask)" = 0022 || exit 72
test "$(stat -c %a "$REPO_DIR/new-secret")" = 600 || exit 73
'''
                p=subprocess.run(['bash'],input=source+body,cwd=root,text=True,capture_output=True,
                    env=os.environ|{'DOCKER_REPO_DIR':str(root),'DOCKER_DEPLOY_HOST':'native-linux',
                                    'SIMULATE_FAILURE':'1' if failed else '0'})
                self.assertEqual(p.returncode,0,p.stderr)

    def test_native_cadvisor_and_compose_use_linux_adapter(self):
        source=SCRIPT.read_text().rsplit('main "$@"',1)[0]
        body='\npython3() { printf "%s\\n" "$@"; }\nif is_windows_compose_stack cadvisor; then exit 90; fi\ncompose config --quiet\n'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'example').mkdir()
            p=subprocess.run(['bash'],input=source+body,cwd=root/'example',text=True,capture_output=True,
                env=os.environ|{'DOCKER_REPO_DIR':str(root),'DOCKER_DEPLOY_HOST':'native-linux'})
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(p.stdout.splitlines(),[str(root/'scripts/native-deploy/compose.py'),'--repo',str(root),'--stack','example','--','config','--quiet'])

    def test_unknown_host_context_stops_before_operations(self):
        p=subprocess.run(['bash',str(SCRIPT)],capture_output=True,text=True,
            env=os.environ|{'DOCKER_DEPLOY_HOST':'unknown'})
        self.assertNotEqual(p.returncode,0)
        self.assertIn('Unsupported deployment host context',p.stderr)
