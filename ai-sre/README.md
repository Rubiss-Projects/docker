# AI SRE staging stack

This stack runs AI SRE in recommendation-only mode and discovers services from existing Docker/Homepage labels. Its dedicated socket proxy exposes read-only container inventory; all Docker mutation endpoints are disabled.

The committed `.env` deliberately leaves AI diagnosis and Discord disabled. Before deployment, add an encrypted `.env.secret` containing `OPENAI_API_KEY`, `GRAFANA_WEBHOOK_SECRET`, `AI_SRE_APPROVAL_SECRET`, `DISCORD_TOKEN`, and `DISCORD_INCIDENT_CHANNEL_ID`, then enable the desired connectors in `.env`.

Grafana provisioning is intentionally added only after the webhook secret exists, so alerts cannot be forwarded with a known placeholder credential.
