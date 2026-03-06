---
name: autobrr-api
description: "Interact with the autobrr API for managing torrent automation — filters, indexers, feeds, download clients, IRC networks, notifications, release history, and config. Use this skill whenever the user mentions autobrr, wants to manage torrent filters, toggle indexers or feeds, configure download clients, check autobrr health, manage IRC networks, or automate any autobrr operations. Also use when the user references torrent automation, RSS/IRC monitoring, or needs to interact with their autobrr instance programmatically."
---

# autobrr API

autobrr is a torrent automation tool that monitors IRC/RSS for new torrents and forwards matches to download clients. This skill covers programmatic interaction with the autobrr REST API.

## Environment

In this infrastructure, autobrr runs as a Docker container:

- **Container name**: `autobrr`
- **Internal URL**: `http://autobrr:7474` (via proxynet Docker network)
- **External URL**: `https://autobrr.benlawson.dev`
- **API base path**: `/api`
- **Config directory**: `./config` (mounted volume)
- **Port**: 7474 (internal and external)

The API key is stored in `/mnt/e/Docker/autobrr/.env` as `AUTOBRR_API_KEY`. It can also be found in the autobrr dashboard under Settings > API Keys.

## Authentication

All API requests require an API key. Two methods:

1. **Header (recommended)**: Include `X-API-Token: <API_KEY>` in the request header
2. **Query parameter**: Append `?apikey=<API_KEY>` to the URL

Always prefer the header method — it avoids exposing the key in logs or browser history.

```bash
# Header method (preferred)
curl -X GET 'http://autobrr:7474/api/filters' -H 'X-API-Token: AUTOBRR_API_KEY'

# Query parameter method
curl -X GET 'http://autobrr:7474/api/filters?apikey=AUTOBRR_API_KEY'
```

## API Endpoint Reference

Base URL: `http://autobrr:7474/api`

| # | Resource | Endpoint | Methods |
|---|----------|----------|---------|
| 1 | Liveness Check | `/healthz/liveness` | GET |
| 2 | Readiness Check | `/healthz/readiness` | GET |
| 3 | Download Clients | `/download_clients` | GET, POST, PUT |
| 4 | Feeds | `/feeds` | GET |
| 5 | Feed Status | `/feeds/<ID>/enabled` | PATCH |
| 6 | Feed Cache | `/feeds/<ID>/cache` | DELETE |
| 7 | Filters | `/filters` | GET, POST |
| 8 | Filter by ID | `/filters/<ID>` | PATCH, DELETE |
| 9 | Filter Status | `/filters/<ID>/enabled` | PUT |
| 10 | Indexers | `/indexer` | GET |
| 11 | Indexer Status | `/indexer/<ID>/enabled` | PATCH |
| 12 | IRC Networks | `/irc` | GET |
| 13 | IRC Restart | `/irc/network/<ID>/restart` | GET |
| 14 | API Keys | `/keys` | GET, POST |
| 15 | Notifications | `/notification` | GET, POST |
| 16 | Release History | `/release` | DELETE |
| 17 | Config | `/config` | GET, PATCH |

---

## Health Checks

### Liveness Check

Checks if autobrr is running.

```bash
curl -X GET 'http://autobrr:7474/api/healthz/liveness' -H 'X-API-Token: AUTOBRR_API_KEY'
```

- **200 OK**: Application is alive

### Readiness Check

Checks if autobrr and its dependencies (database) are ready to accept requests.

```bash
curl -X GET 'http://autobrr:7474/api/healthz/readiness' -H 'X-API-Token: AUTOBRR_API_KEY'
```

- **200 OK**: Ready to accept requests
- **500**: Database unreachable (relevant for Postgres; SQLite typically doesn't have this issue)

---

## Filters

Filters define rules for matching torrents from IRC/RSS sources.

### List all filters

```bash
curl -X GET 'http://autobrr:7474/api/filters' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq '.[] | {id, name}'
```

### Enable or disable a filter

```bash
curl -X PUT 'http://autobrr:7474/api/filters/<FILTER_ID>/enabled' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -d '{"enabled": true}'
```

### Create a filter

```bash
curl -X POST 'http://autobrr:7474/api/filters' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "filter name",
    "enabled": false,
    "resolutions": [],
    "codecs": [],
    "sources": [],
    "containers": [],
    "origins": []
  }'
```

### Update a filter

Use PATCH with the filter ID. The body can include any combination of filter fields:

```bash
curl -X PATCH 'http://autobrr:7474/api/filters/<FILTER_ID>' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "enabled": true,
    "priority": 1,
    "use_regex": false,
    "years": "2023-2030",
    "resolutions": [],
    "sources": [],
    "codecs": [],
    "containers": [],
    "match_hdr": [],
    "except_hdr": [],
    "match_other": [],
    "except_other": [],
    "smart_episode": false,
    "except_releases": "",
    "tags": "tag1,tag2",
    "except_tags": "",
    "match_language": [],
    "except_language": [],
    "formats": ["FLAC"],
    "quality": ["Lossless"],
    "media": [],
    "match_release_types": [],
    "origins": [],
    "except_origins": [],
    "indexers": [
      {"id": 21, "name": "Redacted", "identifier": "redacted"}
    ],
    "actions": [
      {
        "name": "Action name",
        "type": "QBITTORRENT",
        "enabled": true,
        "category": "category",
        "tags": "tags",
        "reannounce_interval": 7,
        "reannounce_max_attempts": 25,
        "client_id": 16
      }
    ],
    "external": [
      {
        "id": 4,
        "name": "webhook",
        "index": 0,
        "type": "WEBHOOK",
        "enabled": true,
        "webhook_host": "http://service:port/hook",
        "webhook_method": "POST",
        "webhook_expect_status": 200
      }
    ]
  }'
```

### Delete a filter

```bash
curl -X DELETE 'http://autobrr:7474/api/filters/<FILTER_ID>' \
  -H 'X-API-Token: AUTOBRR_API_KEY'
```

---

## Indexers

### List all indexers

```bash
curl -X GET 'http://autobrr:7474/api/indexer' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq '.[] | {id, name, enabled}'
```

### Enable or disable an indexer

```bash
curl -X PATCH 'http://autobrr:7474/api/indexer/<INDEXER_ID>/enabled' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -d '{"enabled": true}'
```

---

## IRC Networks

### List all networks

```bash
curl -X GET 'http://autobrr:7474/api/irc' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq '.[] | {id, name, healthy}'
```

### Restart a network

```bash
curl -X GET 'http://autobrr:7474/api/irc/network/<NETWORK_ID>/restart' \
  -H 'X-API-Token: AUTOBRR_API_KEY'
```

---

## Feeds

### List all feeds

```bash
curl -X GET 'http://autobrr:7474/api/feeds' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq '.[] | {id, name, enabled}'
```

### Enable or disable a feed

```bash
curl -X PATCH 'http://autobrr:7474/api/feeds/<FEED_ID>/enabled' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -d '{"enabled": true}'
```

### Clear feed cache

```bash
curl -X DELETE 'http://autobrr:7474/api/feeds/<FEED_ID>/cache' \
  -H 'X-API-Token: AUTOBRR_API_KEY'
```

---

## Download Clients

### List all download clients

```bash
curl -X GET 'http://autobrr:7474/api/download_clients' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq
```

### Add a download client

**qBittorrent:**
```bash
curl -X POST 'http://autobrr:7474/api/download_clients' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "qbit",
    "type": "QBITTORRENT",
    "enabled": true,
    "host": "http://qbittorrent:8080",
    "tls": false,
    "tls_skip_verify": false,
    "username": "username",
    "password": "password",
    "settings": {
      "basic": {
        "auth": true,
        "username": "username",
        "password": "password"
      },
      "rules": {
        "enabled": true,
        "max_active_downloads": 1,
        "ignore_slow_torrents": true,
        "ignore_slow_torrents_condition": "MAX_DOWNLOADS_REACHED",
        "download_speed_threshold": 10000,
        "upload_speed_threshold": 400
      }
    }
  }'
```

**Deluge:**
```bash
curl -X POST 'http://autobrr:7474/api/download_clients' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Deluge",
    "type": "DELUGE_V2",
    "enabled": true,
    "host": "127.0.0.1",
    "port": 12064,
    "tls": false,
    "tls_skip_verify": false,
    "username": "USERNAME",
    "password": "PASSWORD",
    "settings": {
      "basic": {},
      "rules": {
        "enabled": true,
        "max_active_downloads": 2
      }
    }
  }'
```

**Sonarr/Radarr (*arr):**
```bash
curl -X POST 'http://autobrr:7474/api/download_clients' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Sonarr",
    "type": "SONARR",
    "enabled": true,
    "host": "http://sonarr:8989",
    "settings": {
      "apikey": "ARR_API_KEY",
      "basic": {
        "auth": true,
        "username": "USERNAME",
        "password": "PASSWORD"
      },
      "external_download_client_id": 0
    }
  }'
```

Supported client types: `QBITTORRENT`, `DELUGE_V1`, `DELUGE_V2`, `RTORRENT`, `TRANSMISSION`, `SONARR`, `RADARR`, `LIDARR`, `WHISPARR`, `READARR`, `SABNZBD`, `PORLA`.

### Update a download client

Use PUT with the full client object including the `id` field:

```bash
curl -X PUT 'http://autobrr:7474/api/download_clients' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "id": 21,
    "name": "Qbit",
    "type": "QBITTORRENT",
    "enabled": true,
    "host": "http://qbittorrent:8080",
    ...
  }'
```

---

## Notifications

### List all notification agents

```bash
curl -X GET 'http://autobrr:7474/api/notification' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq '.[] | {id, name, type, enabled, events}'
```

### Create a notification agent

Supported types: `DISCORD`, `NOTIFIARR`, `TELEGRAM`, `PUSHOVER`, `GOTIFY`, `NTFY`, `SHOUTRRR`, `LUNASEA`.

Available events: `PUSH_APPROVED`, `PUSH_REJECTED`, `PUSH_ERROR`, `IRC_DISCONNECTED`, `IRC_RECONNECTED`, `APP_UPDATE_AVAILABLE`.

```bash
curl -X POST 'http://autobrr:7474/api/notification' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "enabled": true,
    "name": "Agent Name",
    "type": "DISCORD",
    "events": ["PUSH_APPROVED", "PUSH_REJECTED"],
    "webhook": "https://discord-webhook.url"
  }'
```

Type-specific fields:
- **DISCORD**: `webhook` (webhook URL)
- **TELEGRAM**: `token` (bot token), `channel` (chat ID), `topic` (thread ID)
- **NOTIFIARR**: `api_key`
- **GOTIFY**: `host`, `token` (app token)
- **PUSHOVER**: `api_key`, `token` (user key)
- **NTFY**: `host`, `token`, `topic`

---

## API Keys

### List all API keys

```bash
curl -X GET 'http://autobrr:7474/api/keys' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq 'map(del(.scopes))'
```

### Create a new API key

```bash
curl -X POST 'http://autobrr:7474/api/keys' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"name": "my-new-key", "scopes": []}' | jq 'del(.scopes)'
```

---

## Release History

### Clear release history

Remove release history entries older than the specified number of hours:

```bash
# Clear releases older than 1 year (8760 hours)
curl -X DELETE 'http://autobrr:7474/api/release?olderThan=8760' \
  -H 'X-API-Token: AUTOBRR_API_KEY'
```

---

## Config

### Read the config

```bash
curl -X GET 'http://autobrr:7474/api/config' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq
```

### Change log level

Valid levels: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`

```bash
curl -X PATCH 'http://autobrr:7474/api/config' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"log_level": "TRACE"}'
```

### Enable or disable update check

```bash
curl -X PATCH 'http://autobrr:7474/api/config' \
  -H 'X-API-Token: AUTOBRR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"check_for_updates": true}'
```

---

## Common Patterns

### Health check for monitoring

Use the liveness endpoint for quick checks (Uptime Kuma, n8n workflows) and the readiness endpoint when you need to confirm the database is also healthy.

### Bulk filter management

To enable/disable multiple filters, iterate over filter IDs:

```bash
for id in 1 2 3 4 5; do
  curl -s -X PUT "http://autobrr:7474/api/filters/${id}/enabled" \
    -H 'X-API-Token: AUTOBRR_API_KEY' \
    -d '{"enabled": false}'
done
```

### Integration with n8n

When building n8n workflows that interact with autobrr, use HTTP Request nodes with:
- **Method**: As specified per endpoint
- **URL**: `http://autobrr:7474/api/<endpoint>`
- **Header**: `X-API-Token` = `{{ $env.AUTOBRR_API_KEY }}`
- **Response format**: JSON

### Troubleshooting IRC connections

If an IRC network shows `healthy: false`, restart it:
```bash
# List networks to find the ID
curl -s -X GET 'http://autobrr:7474/api/irc' \
  -H 'X-API-Token: AUTOBRR_API_KEY' | jq '.[] | {id, name, healthy}'

# Restart the unhealthy network
curl -X GET 'http://autobrr:7474/api/irc/network/<NETWORK_ID>/restart' \
  -H 'X-API-Token: AUTOBRR_API_KEY'
```
