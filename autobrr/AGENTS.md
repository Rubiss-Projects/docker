# autobrr Service Guidance

autobrr is a torrent automation tool that monitors IRC announce channels and RSS feeds for new torrents, matching them against user-defined filters and forwarding matches to download clients.

## Service Configuration

- **Container name**: `autobrr`
- **Image**: `ghcr.io/autobrr/autobrr:latest`
- **Port**: 7474
- **Internal URL**: `http://autobrr:7474`
- **External URL**: `https://autobrr.benlawson.dev`
- **Config volume**: `./config:/config`
- **Network**: `proxynet`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TZ` | Timezone (America/Chicago) |
| `AUTOBRR_API_KEY` | API key for autobrr API access |

## API

autobrr exposes a REST API at `/api`. Use the `autobrr-api` skill for full endpoint reference, authentication details, and curl examples. The API key is passed via `X-API-Token` header.

Routine IRC health recovery is deterministic. Grafana evaluates the per-network channel metrics, waits three minutes, and sends a labeled alert to the authenticated `autobrr IRC Recovery Webhook` n8n workflow. The workflow invokes `n8n/scripts/autobrr_irc_recovery.js` for only the labeled provider. `n8n/scripts/autobrr_irc_watchdog.js` runs every five minutes as a missed-alert fallback, requires three consecutive failures, restarts only the affected network, and enforces a 30-minute cooldown.

Provider-specific recovery is implemented by `n8n/scripts/autobrr_irc_recovery.js` and governed by the git-crypt protected `n8n/irc-recovery-policies.json`. Supported branches include deterministic NickServ verification/setup and SASL/no-auth recovery as enabled by private policy. Recovery credentials belong to n8n and are stored in git-crypt protected `n8n/irc-recovery-secrets.json`, separate from Compose dotenv parsing; autobrr's secret overlay contains only secrets consumed directly by autobrr. Provider names, nicks, and provider-specific secret keys must not appear in unencrypted tracked files.

## Homepage Integration

- **Group**: Downloads
- **Widget**: `autobrr` (official widget using API key)

## Uptime Kuma

Monitored via SWAG auto-uptime-kuma labels at `https://autobrr.benlawson.dev/`.

## Key Relationships

- **Download clients**: Forwards matched torrents to qBittorrent, Transmission, Sonarr, Radarr, etc.
- **Prowlarr**: Provides indexer configuration
- **IRC networks**: Monitors announce channels for real-time releases
- **RSS feeds**: Alternative to IRC for torrent source monitoring
