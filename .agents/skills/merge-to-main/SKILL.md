---
name: merge-to-main
description: Prepare, review, and merge changes in this Docker infrastructure repository through a pull request with up to five Codex automated review rounds. Use for committing, publishing, merging, or finishing repository work, including tasks with no intended PR, to leave the self-hosted deployment checkout clean on main.
---

# Merge to main safely

The canonical checkout is `/mnt/e/Docker`. GitHub's self-hosted deployment runner
uses that same checkout. A feature branch or dirty worktree there can break an
unrelated deployment. Changes reach `main` only through a pull request.

## Preserve work and keep the deployment checkout available

- Start by checking branch, status (including untracked files), worktrees, and
  active deployment runs. Do not switch or update a checkout while deployment
  is operating on it; wait for that run to finish.
- Prefer a separate worktree outside the canonical checkout for feature work,
  leaving `/mnt/e/Docker` clean on `main` throughout. Keep repository secrets out
  of PRs and respect git-crypt; do not copy live service data into a worktree.
- Do not discard, stash, commit, or move another person's/agent's changes just to
  achieve a clean status. Coordinate if unrelated work blocks checkout hygiene.
- Preserve intended task changes on a named branch before switching away. Remove
  only your own unintended changes. If no PR is authorized, keep unfinished work
  on that branch/worktree without pushing or merging it; report its location.
- This skill does not authorize creating a PR, publishing work, or merging when
  the user only asked a question or requested local changes.

## Prepare the pull request

1. Review the diff, remove task leftovers, and run focused tests. Follow repository
   guidance for commits; do not add model co-authors.
2. Fetch `origin` and rebase the feature branch onto the latest `origin/main`
   before opening the PR. Re-test affected code after conflict resolution.
3. Commit only intended files and push the feature branch. Open a PR targeting
   `main` with a simple problem/solution summary and validation results.
4. If updating a published branch requires rewriting history, use an explicitly
   checked remote head and `--force-with-lease`, never unconditional force push.
   Do not rewrite a branch shared with someone else without coordination.

## Codex automated review — at most five rounds per PR

- Request Codex automated review on the PR (for the configured GitHub integration,
  post `@codex review`). Count an automatically triggered review as a round too;
  avoid duplicate requests while one is pending.
- Record each round's head SHA and outcome. Inspect published reviews, inline
  comments, and PR comments—not just CI status or an acknowledgment reaction.
- Wait for the review to finish. No response, an unavailable integration, or a
  quota error is **not** a passing review. Report a blocker instead of silently
  substituting self-review or merging without the requested automated review.
- Evaluate feedback for correctness and relevance. Fix actionable defects in
  scope, test, commit, push, and request another review of the new head if rounds
  remain. Explain why non-actionable bot feedback does not warrant a change;
  don't make unrelated changes just to satisfy a suggestion.
- Stop early when the current head has a completed review with no unaddressed
  actionable findings. Five rounds is a ceiling, not a target.
- After round five, do not request round six. If fixes remain, the head has not
  been reviewed, or a material concern is unresolved, leave the PR open and
  report what needs a human decision. The review cap is not permission to merge
  known defects or skip required checks.

## Merge gate: canonical checkout must already be clean on main

Before **every** merge (including enabling auto-merge or adding to a merge queue):

1. Confirm required CI passed for the current PR head, Codex review is complete,
   required human approvals are satisfied, and no actionable feedback or merge
   conflict remains. Refresh GitHub state immediately before merging.
2. Stop editing in the canonical checkout. Ensure intended work is safely on the
   PR branch, then switch `/mnt/e/Docker` to `main`. A feature worktree may remain
   on its feature branch; it is the deployment checkout that must be on `main`.
3. Verify both conditions in the canonical checkout:

   ```bash
   git -C /mnt/e/Docker branch --show-current
   git -C /mnt/e/Docker status --porcelain=v1 --untracked-files=all
   ```

   The branch must be `main` and status output must be empty. Recheck immediately
   before the remote merge. Never bypass this gate with admin merge privileges,
   reset/clean commands, or a direct push to `main`.
4. Merge by explicit PR number/URL, not current-branch inference. Where supported,
   pin the reviewed head with `gh pr merge --match-head-commit <sha>`. If the head
   changes, re-evaluate CI/review state instead of merging unreviewed changes.
5. Observe the merge-triggered deployment. Do not race its checkout operations
   with a local pull, branch switch, or edits. Once it finishes, fetch and
   fast-forward clean local `main` if necessary, then verify status again.

## Closeout applies even without a PR

At task completion, leave the canonical checkout on **clean `main`**, even for
diagnostic work or changes that were not intended to be merged. Preserve pending
work elsewhere rather than discarding it or committing it directly to `main`.
If another agent's work or a deployment prevents safe cleanup, explicitly report
the blocker; do not claim the clean-main requirement was met.

Report the PR/merge result when applicable, review rounds used, tests/deployment
status, any preserved unmerged work, and the final clean-main check.
