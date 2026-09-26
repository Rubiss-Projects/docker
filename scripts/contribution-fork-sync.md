# Contribution fork maintenance

The assistant's GitHub App intentionally cannot write workflows. When upstream
changes `.github/workflows`, a stale contribution fork can make even a normal
source-only contribution fail with GitHub HTTP 403. This host job imports already
trusted upstream history without expanding the App's permissions.

Only these mappings are allowed, always `main` to `main`:

| Upstream | Contribution fork |
| --- | --- |
| `Rubiss-Projects/ai-assistant` | `Rubiss/ai-assistant-contributions` |
| `Rubiss-Projects/docker` | `Rubiss/docker-contributions` |

The script pins repository IDs and fork parentage, requires public, active
repositories with default branch `main`, and refuses to sync if fork Actions are
enabled. It fetches into a temporary bare Git repository and requires the old
fork head to be an ancestor of the pinned upstream head. It checks again before
an ordinary non-force push of that exact SHA to the fork's `refs/heads/main`.
It never checks out or runs repository files, merges, resets, deletes branches,
or updates contribution branches/PRs. Divergence needs operator investigation.

## Host boundary and scheduling

`contribution-fork-sync.timer` is a WSL systemd **user** timer for `rubiss` on
Ben-Server, not a container or an agent tool. It starts 30 seconds after the user
manager starts, then one minute after each run finishes (including failures).
The oneshot process exits between runs; systemd prevents overlapping activations.
The existing Windows watchdog starts WSL/Docker after boot; user lingering keeps
the timer available without an interactive session. A stopped WSL instance does
not run timers; the startup activation catches up when WSL starts again.

Read-only GitHub metadata checks use the operator's existing host `gh` login;
pushes use the existing host SSH identity. No credential is copied, new scope
granted, container mount added, or author/reviewer sandbox capability changed.
The job ignores inherited runner tokens and Git configuration. Its authority is
the trusted host operator's, not the assistant's. Only reviewed upstream code is
deployed here through the existing trusted push-to-main workflow.

Sync is eventually consistent, not a prerequisite built into each contribution.
An immediate publish after upstream changes workflows can still fail briefly;
retry the saved contribution after a successful timer run. This job does not
rebase existing work or create a fresh contribution branch. Network/authentication
errors, changed repository settings and divergence fail closed and are retried
on the next tick. Check the journal if failures persist.

## Operations (WSL, as rubiss)

The main-host deployment workflow installs/refreshes this timer and runs the job
once. Installation requires lingering (`sudo loginctl enable-linger rubiss` if
local policy cannot enable it without prompting), `python3`, `git`, `gh`, a stored
host GitHub login, and noninteractive SSH access to GitHub with a known host key.
No root service or additional dependency is installed.

```bash
# Read-only remote verification; no push unless --apply is explicitly passed.
python3 /mnt/e/Docker/scripts/sync-contribution-forks.py

systemctl --user status contribution-fork-sync.timer contribution-fork-sync.service
journalctl --user -u contribution-fork-sync.service -n 30 --no-pager
systemctl --user start contribution-fork-sync.service
```

Rollback: `systemctl --user disable --now contribution-fork-sync.timer`, then
`systemctl --user stop contribution-fork-sync.service`. Revert the installation
workflow step through a PR to keep later deployments from re-enabling it.
Do **not** rewind synced forks or widen the bot App's permissions to recover.
