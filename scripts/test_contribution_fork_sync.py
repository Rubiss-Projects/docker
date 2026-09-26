"""Real local Git histories exercise the sync boundary without network/credentials."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "fork_sync", Path(__file__).with_name("sync-contribution-forks.py"))
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.upstream = Path(self.temp.name) / "upstream.git"
        self.fork = Path(self.temp.name) / "fork.git"
        self.pair = M.FORKS[0]
        self.commands = []
        self.api_calls = []
        self.overrides = {}
        self.before_push = None
        for directory in (self.upstream, self.fork):
            self.fixture_git("init", "--bare", "--template=", str(directory))
        self.base = self.commit("base")
        self.tip = self.commit("upstream workflow update", self.base)
        self.fixture_git("update-ref", M.REF, self.tip, cwd=self.upstream)
        self.fixture_git("fetch", str(self.upstream), self.base, cwd=self.fork)
        self.fixture_git("update-ref", M.REF, self.base, cwd=self.fork)
        self.fixture_git("update-ref", "refs/heads/ai-assistant/existing", self.base, cwd=self.fork)
        original_run = M.run

        def transport(*args, **kwargs):
            self.commands.append(args)
            if args[0] != "git":
                self.fail("Unexpected external command")
            if "push" in args and self.before_push:
                self.before_push()
            urls = {
                f"https://github.com/{self.pair.upstream}.git": str(self.upstream),
                f"https://github.com/{self.pair.repository}.git": str(self.fork),
                f"git@github.com:{self.pair.repository}.git": str(self.fork),
            }
            # Only the fixture transport enables file://; production forbids it.
            mapped = [urls.get(arg, arg) for arg in args[1:]]
            return original_run("git", "-c", "protocol.file.allow=always", *mapped, **kwargs)

        self.addCleanup(patch.stopall)
        patch.object(M, "run", side_effect=transport).start()
        patch.object(M, "github", side_effect=self.api).start()

    def fixture_git(self, *args, cwd=None, input=None):
        env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
               "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd,
                              input=input, env=env, text=True, capture_output=True,
                              check=True, timeout=10).stdout.strip()

    def commit(self, message, parent=None):
        tree = self.fixture_git("mktree", cwd=self.upstream, input="")
        return self.fixture_git("commit-tree", tree, *(["-p", parent] if parent else []),
                                "-m", message, cwd=self.upstream)

    def ref(self, directory, ref=M.REF):
        return self.fixture_git("rev-parse", ref, cwd=directory)

    def api(self, endpoint):
        self.api_calls.append(endpoint)
        if endpoint in self.overrides:
            return self.overrides[endpoint]
        if endpoint.endswith("/actions/permissions"):
            return {"enabled": False}
        for name, repository_id, directory in (
            (self.pair.upstream, self.pair.upstream_id, self.upstream),
            (self.pair.repository, self.pair.repository_id, self.fork),
        ):
            if endpoint == f"repos/{name}/git/ref/heads/main":
                return {"ref": M.REF, "object": {"type": "commit", "sha": self.ref(directory)}}
            if endpoint == f"repos/{name}":
                return {"id": repository_id, "full_name": name, "default_branch": "main",
                        "private": False, "archived": False, "disabled": False,
                        "fork": directory == self.fork, "parent": {"id": self.pair.upstream_id}}
        self.fail(f"Unexpected API endpoint: {endpoint}")

    def test_default_dry_run_does_not_push(self):
        M.sync(self.pair)
        self.assertEqual(self.ref(self.fork), self.base)
        self.assertFalse(any("push" in command for command in self.commands))

    def test_fast_forward_changes_only_main_and_is_idempotent(self):
        M.sync(self.pair, apply=True)
        self.assertEqual(self.ref(self.fork), self.tip)
        self.assertEqual(self.ref(self.fork, "refs/heads/ai-assistant/existing"), self.base)
        pushes = [command for command in self.commands if "push" in command]
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0][-4:], ("push", "--porcelain",
                         f"git@github.com:{self.pair.repository}.git", f"{self.tip}:{M.REF}"))
        self.commands.clear()
        M.sync(self.pair, apply=True)
        self.assertEqual(self.commands, [])

    def test_diverged_or_ahead_fork_is_not_replaced(self):
        for parent in (self.base, self.tip):
            with self.subTest(parent=parent):
                other = self.commit("fork only", parent)
                self.fixture_git("fetch", str(self.upstream), other, cwd=self.fork)
                self.fixture_git("update-ref", M.REF, other, cwd=self.fork)
                with self.assertRaisesRegex(M.SyncError, "ahead or diverged"):
                    M.sync(self.pair, apply=True)
                self.assertEqual(self.ref(self.fork), other)
        self.assertFalse(any("push" in command for command in self.commands))

    def test_repository_policy_fails_closed(self):
        endpoint = f"repos/{self.pair.repository}"
        valid = self.api(endpoint)
        for field, invalid in (("id", 1), ("full_name", "other/repo"), ("default_branch", "other"),
                               ("private", True), ("archived", True), ("disabled", True),
                               ("fork", False), ("parent", None), ("parent", {"id": 1})):
            with self.subTest(field=field, value=invalid):
                self.overrides[endpoint] = {**valid, field: invalid}
                with self.assertRaises(M.SyncError):
                    M.sync(self.pair, apply=True)
        self.assertEqual(self.commands, [])

    def test_enabled_or_unknown_fork_actions_refuse_sync(self):
        for value in ({"enabled": True}, {}):
            self.overrides[f"repos/{self.pair.repository}/actions/permissions"] = value
            with self.assertRaisesRegex(M.SyncError, "Actions must remain disabled"):
                M.sync(self.pair, apply=True)
        self.assertEqual(self.commands, [])

    def test_invalid_ref_is_not_used_as_an_argument(self):
        self.overrides[f"repos/{self.pair.upstream}/git/ref/heads/main"] = {
            "ref": M.REF, "object": {"type": "commit", "sha": "--upload-pack=malicious"}}
        with self.assertRaisesRegex(M.SyncError, "invalid main ref"):
            M.sync(self.pair, apply=True)
        self.assertEqual(self.commands, [])

    def test_changed_head_is_deferred_before_push(self):
        calls = 0
        original = self.api

        def moving_api(endpoint):
            nonlocal calls
            if endpoint == f"repos/{self.pair.upstream}/git/ref/heads/main":
                calls += 1
                if calls == 2:
                    self.fixture_git("update-ref", M.REF, self.base, cwd=self.upstream)
            return original(endpoint)

        M.github.side_effect = moving_api
        with self.assertRaisesRegex(M.SyncError, "changed during sync"):
            M.sync(self.pair, apply=True)
        self.assertEqual(self.ref(self.fork), self.base)
        self.assertFalse(any("push" in command for command in self.commands))

    def test_non_force_push_rejects_last_moment_divergence(self):
        other = self.commit("concurrent fork change", self.base)

        def move_fork():
            self.fixture_git("fetch", str(self.upstream), other, cwd=self.fork)
            self.fixture_git("update-ref", M.REF, other, cwd=self.fork)

        self.before_push = move_fork
        with self.assertRaises(M.SyncError):
            M.sync(self.pair, apply=True)
        self.assertEqual(self.ref(self.fork), other)


class BoundaryTests(unittest.TestCase):
    def test_failed_fork_cools_down_without_delaying_the_other_fork(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with patch.object(M.time, "time", return_value=1000), patch.object(
                    M, "sync", side_effect=[M.SyncError("offline"), None]):
                self.assertEqual(M.sync_all(apply=True, state_directory=state), 1)
            retry = state / f"{M.FORKS[0].repository_id}.retry"
            self.assertEqual(retry.read_text(), str(1000 + M.RETRY_SECONDS))
            with patch.object(M.time, "time", return_value=1001), patch.object(M, "sync") as sync:
                self.assertEqual(M.sync_all(apply=True, state_directory=state), 1)
                sync.assert_called_once_with(M.FORKS[1], apply=True)
            with patch.object(M.time, "time", return_value=1000 + M.RETRY_SECONDS), patch.object(M, "sync") as sync:
                self.assertEqual(M.sync_all(apply=True, state_directory=state), 0)
                self.assertEqual(sync.call_count, 2)
            self.assertFalse(retry.exists())

    def test_invalid_retry_state_does_not_start_network_work_for_that_fork(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / f"{M.FORKS[0].repository_id}.retry").write_text("invalid")
            with patch.object(M, "sync") as sync:
                self.assertEqual(M.sync_all(apply=True, state_directory=state), 1)
                sync.assert_called_once_with(M.FORKS[1], apply=True)

    def test_environment_does_not_inherit_credentials_or_git_overrides(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "private", "GH_TOKEN": "private",
                                    "GIT_CONFIG_COUNT": "1", "GIT_DIR": "/unexpected"}):
            env = M.environment()
        for key in ("GH_TOKEN", "GITHUB_TOKEN", "GIT_CONFIG_COUNT", "GIT_DIR"):
            self.assertNotIn(key, env)

    def test_github_api_is_explicitly_read_only(self):
        with patch.object(M, "run", return_value=subprocess.CompletedProcess([], 0, '{"id": 1}')) as run:
            self.assertEqual(M.github("repos/example/repo"), {"id": 1})
        self.assertEqual(run.call_args.args,
                         ("gh", "api", "--hostname", "github.com", "--method", "GET", "repos/example/repo"))

    def test_error_does_not_expose_transport_output(self):
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 1, "secret output", "secret error")):
            with self.assertRaisesRegex(M.SyncError, r"^gh api failed \(exit 1\)$"):
                M.run("gh", "api")

    def test_cli_defaults_to_dry_run_and_continues_other_fork_on_error(self):
        with patch.object(sys, "argv", ["sync-contribution-forks.py"]), patch.object(
                M, "sync", side_effect=[M.SyncError("offline"), None]) as sync:
            self.assertEqual(M.main(), 1)
        self.assertEqual(sync.call_args_list,
                         [unittest.mock.call(fork, apply=False) for fork in M.FORKS])


if __name__ == "__main__":
    unittest.main()
