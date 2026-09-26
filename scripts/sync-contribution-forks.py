#!/usr/bin/env python3
"""Advance the two contribution forks from trusted upstream main, never agent input."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


@dataclass(frozen=True)
class Fork:
    upstream: str
    upstream_id: int
    repository: str
    repository_id: int


FORKS = (
    Fork("Rubiss-Projects/ai-assistant", 1325664430,
         "Rubiss/ai-assistant-contributions", 1384610047),
    Fork("Rubiss-Projects/docker", 544613323,
         "Rubiss/docker-contributions", 1384610118),
)
REF = "refs/heads/main"


class SyncError(Exception):
    pass


def environment():
    # Use only the operator's stored gh/SSH login, never a runner token, agent
    # environment, Git credential helper, URL rewrite, or inherited Git config.
    return {
        "HOME": str(Path.home()),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "GH_PROMPT_DISABLED": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15",
    }


def run(*args, cwd=None, allowed=(0,)):
    try:
        result = subprocess.run(args, cwd=cwd, env=environment(), text=True,
                                capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SyncError(f"{args[0]} unavailable or timed out") from error
    if result.returncode not in allowed:
        # Do not copy credential-bearing transport diagnostics into the journal.
        raise SyncError(f"{args[0]} {args[1]} failed (exit {result.returncode})")
    return result


def github(endpoint):
    result = run("gh", "api", "--hostname", "github.com", "--method", "GET", endpoint)
    try:
        value = json.loads(result.stdout)
    except ValueError as error:
        raise SyncError("Invalid GitHub API response") from error
    if not isinstance(value, dict):
        raise SyncError("Expected a GitHub API object")
    return value


def verify_repositories(fork):
    for name, repository_id in ((fork.upstream, fork.upstream_id),
                                (fork.repository, fork.repository_id)):
        repo = github(f"repos/{name}")
        if (repo.get("id") != repository_id or repo.get("full_name") != name
                or repo.get("default_branch") != "main"
                or repo.get("private") is not False
                or repo.get("archived") is not False
                or repo.get("disabled") is not False):
            raise SyncError(f"Repository identity/state changed: {name}")
        if name == fork.repository:
            parent = repo.get("parent")
            if (repo.get("fork") is not True or not isinstance(parent, dict)
                    or parent.get("id") != fork.upstream_id):
                raise SyncError(f"Fork parent changed: {name}")
    if github(f"repos/{fork.repository}/actions/permissions").get("enabled") is not False:
        raise SyncError("Fork Actions must remain disabled before importing upstream workflows")


def head(repository):
    value = github(f"repos/{repository}/git/ref/heads/main")
    obj = value.get("object")
    if (value.get("ref") != REF or not isinstance(obj, dict)
            or obj.get("type") != "commit"
            or not isinstance(obj.get("sha"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", obj["sha"])):
        raise SyncError(f"Missing or invalid main ref: {repository}")
    return obj["sha"]


def git(directory, *args, allowed=(0,)):
    return run("git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never",
               "-c", "protocol.https.allow=always", "-c", "protocol.ssh.allow=always",
               "-c", "http.followRedirects=false", *args, cwd=directory, allowed=allowed)


def sync(fork, apply=False):
    verify_repositories(fork)
    source = head(fork.upstream)
    destination = head(fork.repository)
    if source == destination:
        print(f"{fork.repository}: current at {source}", flush=True)
        return

    # A disposable bare object store: no worktree, checkout, hooks, submodules,
    # builds, or execution of files from either repository.
    with tempfile.TemporaryDirectory(prefix="contribution-fork-sync-") as directory:
        git(directory, "init", "--bare", "--template=", ".")
        git(directory, "fetch", "--no-tags", f"https://github.com/{fork.upstream}.git", source)
        git(directory, "fetch", "--no-tags", f"https://github.com/{fork.repository}.git", destination)
        if git(directory, "merge-base", "--is-ancestor", destination, source,
               allowed=(0, 1)).returncode != 0:
            raise SyncError("Fork main is ahead or diverged; refusing to replace its history")

        if not apply:
            print(f"{fork.repository}: would fast-forward {destination} -> {source}", flush=True)
            return

        # Recheck policy and both refs after fetching. A concurrent non-FF update
        # after this check is still rejected by Git's ordinary (non-force) push.
        verify_repositories(fork)
        if head(fork.upstream) != source or head(fork.repository) != destination:
            raise SyncError("Main changed during sync; leaving it for the next run")
        git(directory, "push", "--porcelain", f"git@github.com:{fork.repository}.git",
            f"{source}:{REF}")
        if head(fork.repository) != source:
            raise SyncError("Fork main moved after push; inspect before retrying")
        print(f"{fork.repository}: fast-forwarded {destination} -> {source}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Push verified fast-forwards (default: dry run)")
    args = parser.parse_args()
    failed = False
    for fork in FORKS:
        try:
            sync(fork, apply=args.apply)
        except SyncError as error:
            failed = True
            print(f"{fork.repository}: ERROR: {error}", file=sys.stderr, flush=True)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
