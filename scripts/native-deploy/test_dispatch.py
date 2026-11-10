import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'deploy-changed-service-folders.sh'


@unittest.skipIf(os.name=='nt','Native dispatch requires POSIX bash')
class DispatchTests(unittest.TestCase):
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
