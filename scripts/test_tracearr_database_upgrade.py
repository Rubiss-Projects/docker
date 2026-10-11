"""Exercise database-upgrade ordering and fail-closed behavior without a database."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent.parent / "tracearr/upgrade-database.sh"


@unittest.skipIf(os.name == "nt", "requires POSIX bash")
class TracearrDatabaseUpgradeTests(unittest.TestCase):
    def run_upgrade(self, failure="", current="old", pending="0", state="running"):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "calls"
            stub = r'''
set -Eeuo pipefail
compose() {
  printf '%s\n' "$*" >> "$CALLS"
  case "$*" in
    'config --format json') printf '%s\n' '{"services":{"timescale":{"image":"vendor/db:pg18@sha256:abc"}}}' ;;
    *pg_available_extensions*) printf '%s\n' "$PENDING" ;;
    *pg_dump*) [[ "$FAILURE" != backup ]] || return 3; printf 'archive' ;;
    *pg_restore*) [[ "$FAILURE" != verify ]] || return 4; cat >/dev/null ;;
    'up '*) [[ "$FAILURE" != startup ]] || return 5 ;;
    *'ALTER EXTENSION'*) [[ "$FAILURE" != migration ]] || return 6 ;;
  esac
}
docker() {
  printf 'docker %s\n' "$*" >> "$CALLS"
  case "$1" in
    image) printf 'new\n' ;;
    ps) [[ "$STATE" == missing ]] || printf 'container-id\n' ;;
    inspect)
      if [[ "$*" == *State.Running* ]]; then
        [[ "$STATE" != stopped ]] && printf 'true\n' || printf 'false\n'
      else printf '%s\n' "$CURRENT"; fi ;;
    volume) [[ "$FAILURE" != volume ]] || return 7 ;;
    run) [[ "$FAILURE" != cold-backup ]] || return 8; tar -cf - --files-from /dev/null ;;
  esac
}
log() { :; }
source "$UPGRADE_SCRIPT"
upgrade_tracearr_database
printf 'resume-app\n' >> "$CALLS"
'''
            result = subprocess.run(["bash", "-c", stub], capture_output=True, text=True, env=os.environ | {
                "CALLS": str(log), "FAILURE": failure, "CURRENT": current, "PENDING": pending, "STATE": state,
                "UPGRADE_SCRIPT": str(SCRIPT), "DOCKER_TRACEARR_BACKUP_DIR": directory,
            })
            return result, log.read_text().splitlines()

    def test_backup_and_migration_precede_application_resume(self):
        result, calls = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(next(i for i, c in enumerate(calls) if "pg_restore" in c), calls.index("stop tracearr"))
        self.assertLess(calls.index("stop tracearr"), next(i for i, c in enumerate(calls) if c.startswith("up ")))
        self.assertIn("ALTER EXTENSION timescaledb UPDATE", calls[-2])
        self.assertEqual(calls[-1], "resume-app")

    def test_failures_never_resume_application(self):
        for failure in ["backup", "verify", "startup", "migration"]:
            with self.subTest(failure=failure):
                result, calls = self.run_upgrade(failure=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("resume-app", calls)
                if failure in {"backup", "verify"}:
                    self.assertNotIn("stop tracearr", calls)

    def test_unchanged_database_is_left_running_but_incomplete_migration_is_retried(self):
        result, calls = self.run_upgrade(current="new")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("stop tracearr", calls)
        result, calls = self.run_upgrade(current="new", pending="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stop tracearr", calls)

    def test_stopped_database_starts_old_container_before_dumping(self):
        result, calls = self.run_upgrade(state="stopped")
        self.assertEqual(result.returncode, 0, result.stderr)
        start = calls.index("start --wait --wait-timeout 180 timescale")
        self.assertLess(start, next(i for i, c in enumerate(calls) if "pg_dump" in c))
        self.assertLess(start, next(i for i, c in enumerate(calls) if "pg_available_extensions" in c))

    def test_removed_container_requires_cold_backup_before_creating_database(self):
        result, calls = self.run_upgrade(state="missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(next(i for i, c in enumerate(calls) if c.startswith("docker run ")), next(i for i, c in enumerate(calls) if c.startswith("up ")))
        for failure in ["volume", "cold-backup"]:
            with self.subTest(failure=failure):
                result, calls = self.run_upgrade(state="missing", failure=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(c.startswith("up ") for c in calls))
                self.assertNotIn("resume-app", calls)


if __name__ == "__main__":
    unittest.main()
