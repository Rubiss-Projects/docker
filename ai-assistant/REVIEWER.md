# Codex review worker

The `reviewer` service runs a small private Unix-socket listener. A Codex CLI
process starts only when the assistant queues a review of an owned bot PR.
The host posts the result using its scoped GitHub App; the reviewer never receives
GitHub or Discord credentials. This is server-side Codex with a ChatGPT login,
not GitHub Actions, an OpenAI API key, or the hosted Codex GitHub integration.

The `ai-assistant-review-data` volume was provisioned with a separate ChatGPT login
before enabling this service. To renew it, use the normal native login flow:

```sh
docker compose exec reviewer /usr/local/lib/codex/bin/codex login --device-auth
```

Keep login state separate from the assistant's live `auth.json`; do not copy or
share refresh tokens between concurrent clients. Never include `.env.secret` in
the reviewer's environment. The socket is mode 0600 in a private volume shared
only with the assistant; no TCP endpoint or host port exists. Neither the browser
nor agent workspaces receive that volume.

Reviews use the account's Codex allowance. The native worker rejects API keys
and endpoint overrides and fails closed if login or subscription access fails.
Its read-only command sandbox has no network, apps, MCP, plugins, or repository
instructions. Static review does not replace the author's tests or human approval.

Both the host and worker enforce `CODEX_REVIEW_LIMIT` from the public `.env`:
20 attempts per PR by default, including failed/interrupted attempts; `0` means
unlimited. Blank/unset uses 20; invalid values fail startup. Compose passes one
value to both services. Redeploy both after changing it; existing shared sessions
refresh their instructions/capabilities on their next turn. Raising or lowering
the limit does not reset prior attempts. Unlimited retains the 5,000-record
history caps, single-review concurrency, sandbox restrictions, and timeouts, and
can consume more of the account's Codex allowance.

Stop after a completed review of the current head has no actionable findings.
The quota is a ceiling, not a target: repeated requests, including `retry: true`,
reuse a completed snapshot rather than spend another review. Genuine published
fixes queue a review of the new head.

Keep the assistant's
`github-contributions.json.reviews.json` and the worker's `/data/review-jobs` when
upgrading or rolling back. Interrupted inference is not automatically repeated;
ambiguous GitHub publication is reconciled by its unique marker. Do not delete
ledgers or make no-op commits/new PRs to reset a review budget.

To disable, set `AI_ASSISTANT_ENABLE_CODEX_REVIEWS=false` and redeploy. Existing
sessions refresh their shared context at the next turn; contributions otherwise
keep working. Do not delete either persistent volume. To roll back this limits
rollout, promote v1.20.0 for all three services through the normal reviewed PR.
That version ignores these variables and restores the five-attempt ceilings;
it retains the existing reviewer service and state format. Preserve both review
ledgers and volumes.
