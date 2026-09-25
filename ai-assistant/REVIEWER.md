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

Both the host and worker persist a five-attempt limit per PR. Keep the assistant's
`github-contributions.json.reviews.json` and the worker's `/data/review-jobs` when
upgrading or rolling back. Interrupted inference is not automatically repeated;
ambiguous GitHub publication is reconciled by its unique marker. Do not delete
ledgers or make no-op commits/new PRs to reset a review budget.

To disable, set `AI_ASSISTANT_ENABLE_CODEX_REVIEWS=false` and redeploy. Existing
sessions refresh their shared context at the next turn; contributions otherwise
keep working. Do not delete either persistent volume. The previous compatible
application version for this rollout is v1.17.0; remove the reviewer dependency,
service, and its deployment-readiness probes when promoting that older image,
which has no review-worker entrypoint. Preserve both review ledgers and volumes.
