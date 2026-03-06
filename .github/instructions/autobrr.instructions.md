---
applyTo: "autobrr/**"
---

# autobrr Service Instructions

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
