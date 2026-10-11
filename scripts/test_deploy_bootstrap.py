"""A stale canonical checkout must execute the deployment commit's new safety code."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/deploy-service-changes.yml"


@unittest.skipIf(os.name == "nt", "requires POSIX bash")
class DeployBootstrapTests(unittest.TestCase):
    def test_both_hosts_load_target_script_without_changing_canonical_checkout(self):
        workflow = yaml.safe_load(WORKFLOW.read_text())
        for job in ["deploy-main", "deploy-pi"]:
            with self.subTest(job=job), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo = root / "repo"
                repo.mkdir()

                def git(*args):
                    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL, text=True).strip()

                git("init")
                git("config", "user.name", "Test")
                git("config", "user.email", "test@example.invalid")
                (repo / "scripts").mkdir()
                script = repo / "scripts/deploy-changed-service-folders.sh"
                script.write_text("exit 42\n")
                git("add", ".")
                git("-c", "commit.gpgsign=false", "commit", "-m", "old helper")
                before = git("rev-parse", "HEAD")
                script.write_text('printf "%s\\n" "$@" > "$BOOTSTRAP_RESULT"\n')
                git("add", ".")
                git("-c", "commit.gpgsign=false", "commit", "-m", "new helper")
                after = git("rev-parse", "HEAD")
                git("checkout", "--detach", before)
                git("remote", "add", "origin", str(repo))
                result_file = root / "result"
                command = workflow["jobs"][job]["steps"][0]["run"]
                command = command.replace("${{ github.sha }}", after).replace("${{ github.event.before }}", before)
                result = subprocess.run(["bash", "-c", command], capture_output=True, text=True, env=os.environ | {
                    "DOCKER_REPO_DIR": str(repo), "RUNNER_TEMP": str(root), "BOOTSTRAP_RESULT": str(result_file),
                })
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result_file.read_text().splitlines(), [before, after])
                self.assertEqual(git("rev-parse", "HEAD"), before)
                self.assertEqual(script.read_text(), "exit 42\n")
                self.assertEqual(list(root.glob("deploy-service-folders.*.sh")), [])


if __name__ == "__main__":
    unittest.main()
