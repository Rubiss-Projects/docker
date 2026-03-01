---
applyTo: "cross-seed/**"
---

# Cross-Seed Service Instructions

Cross-seed is an automated cross-seeding tool that finds matching torrents across private trackers and injects them into your torrent client. It runs as a daemon in Docker, continuously monitoring for new downloads and cross-seeding them automatically.

**Documentation**: https://www.cross-seed.org/docs/basics/getting-started  
**GitHub**: https://github.com/cross-seed/cross-seed  
**Discord**: https://discord.gg/jpbUFzS5Wb

---

## Architecture & How It Works

1. **Torrent-based matching**: Analyzes `.torrent` files (from your client or `torrentDir`) and searches Torznab indexers for matching releases on other trackers.
2. **Data-based matching**: Scans actual files on disk (`dataDirs`) to find cross-seedable releases even without `.torrent` files.
3. **RSS scanning**: Periodically pulls RSS feeds from configured Torznab indexers to find new cross-seedable uploads.
4. **Announce matching**: Receives IRC announces via autobrr to match new uploads in real-time.
5. **Webhook searches**: Triggered by torrent client on download completion to immediately search for cross-seeds.

Torrent-based matching always takes priority over data-based when both are available. Data-based matching is supplementary.

---

## Current Setup

### Docker Compose

- **Image**: `ghcr.io/cross-seed/cross-seed:6` (v6 release line)
- **Container name**: `cross-seed` (matches folder name per project convention)
- **User**: `1000:1000` — MUST match the torrent client's user/group
- **Port**: `2468:2468` (HTTP API for webhooks, announce, and job triggers)
- **Command**: `daemon` (runs as a persistent background service)
- **Network**: `proxynet` (shared Docker network for inter-container communication)

### Volumes

| Container Path | Host Path | Purpose |
|---|---|---|
| `/config` | `./config` | Config file, database, logs, torrent cache |
| `/data` | `../../Media` | Single parent volume for downloads + cross-seed links |

**CRITICAL**: Cross-seed and the torrent client MUST share the same volume mount **at the same container path** for hardlinking and injection to work. Docker treats separate volumes as separate filesystems — hardlinks cannot cross volume boundaries. Both cross-seed and Transmission mount `../../Media` at `/data`. This single parent volume ensures `linkDirs` (`/data/cross-seed-links`) and download data (`/data/downloads`) are on the same filesystem, enabling hardlinks.

### Key Paths (Inside Container)

| Path | Purpose |
|---|---|
| `/config/config.js` | Main configuration file |
| `/config/config.db` | SQLite database (search history, cache) |
| `/config/torrent_cache/` | Snatched `.torrent` file cache |
| `/config/logs/` | Log files (`verbose.current.log` for debugging) |
| `/data/downloads` | Torrent download directory (matches Transmission) |
| `/data/cross-seed-links` | Hardlink destination for cross-seeded files |

---

## Configuration Reference (`config.js`)

The config file uses JavaScript module syntax. **NEVER remove options from the config file** — this causes errors. Just set unwanted options to their default values.

### Sensitive Options (Top of File)

| Option | Current Value | Notes |
|---|---|---|
| `apiKey` | `undefined` | Auto-generated; retrieve with `cross-seed api-key` |
| `torznab` | `[]` (template entries) | One URL per Prowlarr indexer: `http://prowlarr:9696/{id}/api?apikey={key}` |
| `sonarr` | `["http://sonarr:8989?apikey=..."]` | Enables ID-based searching via IMDb/TVDB IDs |
| `radarr` | `["http://radarr:7878?apikey=..."]` | Enables ID-based searching via IMDb/TMDB IDs |
| `torrentClients` | `["transmission:http://transmission:9091/transmission/rpc"]` | Prefix with client type. Add `readonly:` after prefix to only source, not inject |

### Matching & Injection Options

| Option | Default | Current | Notes |
|---|---|---|---|
| `matchMode` | `flexible` | `flexible` | `strict` = exact match (no linking needed); `flexible` = allows renames (recommended default); `partial` = allows missing small files (requires linking) |
| `skipRecheck` | `true` | `false` | `false` = always verify data matches before seeding. Prevents reporting false stats |
| `action` | `inject` | `inject` | `inject` = auto-add to client; `save` = save `.torrent` files only |
| `linkType` | `hardlink` | `hardlink` | Options: `hardlink`, `symlink`, `reflink`. Hardlink recommended |
| `linkCategory` | `cross-seed-link` | `cross-seed-data` | Category assigned to injected torrents in client |
| `linkDirs` | `[]` | `["/data/cross-seed-links"]` | Where hardlinks are created. Must be on same volume as data |
| `flatLinking` | `false` | `false` | `false` = organize links into tracker-specific subfolders (recommended) |
| `duplicateCategories` | `false` | `false` | Set `true` if using Arr apps without linking to prevent import queue duplication |
| `useClientTorrents` | `true` | `true` | Query client API for matches (preferred over `torrentDir`) |

### Data & Search Options

| Option | Default | Current | Notes |
|---|---|---|---|
| `dataDirs` | `[]` | `[]` | Directories to scan for data-based matching (disabled; using `useClientTorrents: true` instead) |
| `maxDataDepth` | `2` | `2` | How deep into dataDirs to search. See docs for structure-specific values |
| `outputDir` | `null` | `null` | Retry/save directory. Keep `null` for best experience (maps to config dir). Only set a path if using `action: "save"` |
| `torrentDir` | `null` | `null` | Not needed when `useClientTorrents: true` |

### Timing & Cadence Options

| Option | Default | Current | Notes |
|---|---|---|---|
| `delay` | `30` | `30` | Seconds between searches. Higher = friendlier to trackers |
| `rssCadence` | `30 minutes` | `15 minutes` | How often to scan RSS feeds. Min 10 minutes |
| `searchCadence` | `1 day` | `1 day` | How often to run bulk searches. Official docs warn against setting above 1 day |
| `excludeOlder` | `2 weeks` | `365 days` | Skip torrents first seen longer ago than this |
| `excludeRecentSearch` | `3 days` | `73 days` | Skip torrents searched more recently than this |
| `searchLimit` | `400` | `400` | Max searches per batch per indexer |
| `snatchTimeout` | `30 seconds` | `30 seconds` | Timeout for `.torrent` file downloads |
| `searchTimeout` | `2 minutes` | `2 minutes` | Timeout for search queries |

**Relationship constraint**: `excludeOlder` must be 2-5x `excludeRecentSearch`.

### Episode & Content Options

| Option | Default | Current | Notes |
|---|---|---|---|
| `includeSingleEpisodes` | `false` | `false` | Keep `false` in config, override via webhook with `includeSingleEpisodes=true` |
| `includeNonVideos` | `false` | `false` | Set `true` for music, books, games |
| `seasonFromEpisodes` | `1` | `1` | Match season packs from episodes. Values < 1 require `matchMode: "partial"` |
| `fuzzySizeThreshold` | `0.02` | `0.02` | Size variance tolerance (2%) |
| `autoResumeMaxDownload` | `52428800` | `52428800` | Max bytes remaining to auto-resume (50 MiB) |
| `ignoreNonRelevantFilesToResume` | `false` | `false` | Auto-resume if only nfo/srt/sample files are missing |

### Other Options

| Option | Default | Current | Notes |
|---|---|---|---|
| `host` | `0.0.0.0` | `0.0.0.0` | Bind address for HTTP API |
| `port` | `2468` | `2468` | HTTP API port |
| `notificationWebhookUrls` | `[]` | `[]` | Apprise/Notifiarr webhook URLs |
| `blockList` | `[]` | `[]` | Exclude by name, folder, category, tag, tracker, infoHash, size |

---

## Prowlarr Integration

### Torznab URLs

Each Prowlarr indexer has a numeric ID. The Torznab URL format is:
```
http://prowlarr:9696/{indexer_id}/api?apikey={prowlarr_api_key}
```

- Use container hostname `prowlarr` (not localhost) since both are on `proxynet`
- Get the indexer ID from the Prowlarr UI by clicking the indexer name
- API key is found under Settings → General in Prowlarr

### Cross-Seed Sync Profile (Preventing Leeching)

To use indexers for cross-seeding only (not for Sonarr/Radarr downloads):

1. In Prowlarr: **Settings → Apps → Sync Profiles**
2. Create profile named "Cross-Seed" with:
   - Enable RSS: **No**
   - Enable Interactive Search: **No**
   - Enable Automatic Search: **No**
3. Assign this profile to indexers used only for cross-seeding

This prevents Sonarr/Radarr from using these indexers while cross-seed can still query them via Torznab.

### Freeleech Considerations

If using "Freeleech Only" on an indexer in Prowlarr, create a **second** indexer entry for the same tracker with the Cross-Seed sync profile (no freeleech filter). This ensures cross-seed can search all torrents while Sonarr/Radarr only grab freeleech.

---

## Sonarr & Radarr Integration (ID-Based Searching)

Cross-seed queries Sonarr/Radarr to look up IMDb, TVDB, TMDB, and TVMaze IDs for content. This results in:
- More accurate matches (ID vs text search)
- Fewer unnecessary snatches
- Less load on trackers

**Requirements**: Sonarr v4+, Radarr v3+

URL format: `http://{container_name}:{port}?apikey={api_key}`

The series/movie must exist in Sonarr/Radarr (even if "Missing" or "Unmonitored"), but doesn't need actual media imported.

---

## Torrent Client Integration (Transmission)

Format: `transmission:http://transmission:9091/transmission/rpc`

- Add `readonly:` after the prefix to only source cross-seeds (no injection): `transmission:readonly:http://...`
- Cross-seed must share the same user/group (1000:1000) as the torrent client
- After changing clients, run `cross-seed clear-client-cache`

---

## Linking

### Hardlinks (Current Setup)

Hardlinks are the default and recommended link type:
- Resilient to file moves (won't break if original is relocated)
- Data persists until ALL hardlinks are removed
- **Must be on the same filesystem/Docker volume**

### Link Directory Structure (flatLinking: false)

```
/data/cross-seed-links/
├── TrackerA/
│   ├── Movie.mkv
├── TrackerB/
│   ├── Movie.mkv
│   ├── Show S01/
│   │   ├── Show S01E01.mkv
```

### Requirements for Linking in Docker

1. Cross-seed and torrent client mount the **same Docker volume** for data (both mount `../../Media:/data`)
2. Both see the **same path** for the data and linkDirs (`/data/downloads` and `/data/cross-seed-links`)
3. linkDirs MUST be a **sibling** of the downloads directory under the same parent mount — **NOT** a child of torrentDir/dataDirs/outputDir
4. linkDirs MUST NOT be on a separate bind mount (causes EXDEV cross-device link errors)

### Sonarr/Radarr Volume Architecture

All media services now share the same single parent volume mount pattern for hardlink compatibility:

| Service | Volume Mount |
|---|---|
| Transmission | `../../Media:/data` |
| Cross-seed | `../../Media:/data` |
| Sonarr | `../../Media:/data` |
| Radarr | `../../Media:/data` |
| Bazarr | `../../Media:/data` |
| Unpackerr | `../../Media:/data` |

Because all services mount `../../Media` at `/data`, they all see the same filesystem paths:
- Downloads at `/data/downloads`
- TV library at `/data/tv`
- Movies library at `/data/movies`
- Cross-seed links at `/data/cross-seed-links`

**No remote path mappings are needed.** Sonarr/Radarr see Transmission's downloads at `/data/downloads` directly since they share the same mount.

---

## Partial Matching

Partial matching (`matchMode: "partial"`) captures torrents that are similar but may differ in small files (`.nfo`, `.srt`, `sample`). **Requires linking to be enabled.**

When a partial match is found:
1. Torrent is injected with matched files
2. Torrent is rechecked for missing files
3. Auto-resumed based on `autoResumeMaxDownload` and `ignoreNonRelevantFilesToResume`

To enable:
```javascript
matchMode: "partial",
fuzzySizeThreshold: 0.1,        // optional: higher = more lenient
autoResumeMaxDownload: 52428800, // 50 MiB max remaining
ignoreNonRelevantFilesToResume: true, // resume if only nfo/srt missing
seasonFromEpisodes: 0.8,        // optional: match season packs with 80%+ episodes
```

---

## HTTP API

Base URL: `http://cross-seed:2468` (internal) or `http://localhost:2468` (host)

### Endpoints

| Method | Endpoint | Purpose | Auth Required |
|---|---|---|---|
| GET | `/api/ping` | Health check (returns 200 OK) | No |
| POST | `/api/webhook` | Trigger search for specific torrent | Yes |
| POST | `/api/announce` | Push IRC announces for matching | Yes |
| POST | `/api/job` | Trigger scheduled jobs early | Yes |

### Authentication

Include API key as query param or header:
```bash
curl -XPOST http://cross-seed:2468/api/webhook?apikey=YOUR_API_KEY --data-urlencode "infoHash=${INFO_HASH}"
# or
curl -XPOST http://cross-seed:2468/api/webhook -H "X-Api-Key: YOUR_API_KEY" --data-urlencode "infoHash=${INFO_HASH}"
```

### Webhook (Download Completion)

```bash
curl -XPOST http://cross-seed:2468/api/webhook?apikey=YOUR_API_KEY \
  --data-urlencode "infoHash=${INFO_HASH}" \
  -d "includeSingleEpisodes=true"
```

### Job API (Trigger Searches/RSS Early)

```bash
# Trigger search
curl -XPOST http://cross-seed:2468/api/job?apikey=YOUR_API_KEY -d 'name=search'

# Trigger search ignoring time exclusions
curl -XPOST http://cross-seed:2468/api/job?apikey=YOUR_API_KEY \
  -d 'name=search' \
  -d 'ignoreExcludeRecentSearch=true' \
  -d 'ignoreExcludeOlder=true'

# Available jobs: cleanup, inject, rss, search, updateIndexerCaps
```

### Announce API (autobrr Integration)

```bash
curl -XPOST http://cross-seed:2468/api/announce?apikey=YOUR_API_KEY \
  -H 'Content-Type: application/json' \
  --data '{"name":"torrent.name","guid":"download-link","link":"download-link","tracker":"tracker-name"}'
```

Response codes: `200` = matched and complete, `202` = matched but source still downloading, `204` = no match found.

---

## Utility Commands

Run inside the container: `docker exec -it cross-seed <command>`

| Command | Purpose |
|---|---|
| `cross-seed api-key` | Show the auto-generated API key |
| `cross-seed reset-api-key` | Generate a new API key |
| `cross-seed gen-config` | Generate a new config template |
| `cross-seed diff <a.torrent> <b.torrent>` | Compare two torrents to see why they match/don't |
| `cross-seed tree <file.torrent>` | View torrent file tree from cross-seed's perspective |
| `cross-seed inject` | Manually inject saved `.torrent` files from outputDir |
| `cross-seed inject --inject-dir /path` | Inject from a custom directory |
| `cross-seed clear-cache` | Reset search timestamps (use sparingly) |
| `cross-seed clear-client-cache` | Clear torrent client cache (after changing clients) |
| `cross-seed clear-indexer-failures` | Clear indexer failure history |
| `cross-seed test-notification` | Test notification webhook |
| `cross-seed restore` | Restore cross-seeds from torrent_cache |

**DANGER**: Never run `cross-seed search` or `cross-seed rss` while the daemon is running — it corrupts the SQLite database. Use the `/api/job` endpoint instead.

---

## Adding New Trackers

1. Add the indexer to Prowlarr with the "Cross-Seed" sync profile
2. Add the Torznab URL to the `torznab` array in `config.js`
3. Restart cross-seed: `docker restart cross-seed`
4. Cross-seed automatically queues searches for the new indexer
5. To trigger an immediate search:
   ```bash
   docker exec -it cross-seed curl -XPOST http://localhost:2468/api/job?apikey=YOUR_API_KEY -d 'name=search'
   ```

---

## Troubleshooting

### Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| "missing files" error on injected torrents | Path mismatch between cross-seed and torrent client | Ensure both use same volume mount with same paths |
| "error parsing torrent" | Rate limited by tracker or broken download link | Wait and retry; nothing cross-seed can fix |
| "it has a different file tree" | Files differ between trackers (extra nfo, srt) | Enable `matchMode: "partial"` |
| `SyntaxError: Unexpected identifier` | Missing comma or quote in config.js | Check syntax before the line mentioned in error |
| `outputDir should only contain .torrent files` | outputDir has non-torrent files | Set `outputDir: null` or clean the directory |
| Tracker complaints about snatches | Too many API hits | Reduce `searchLimit`, increase `excludeRecentSearch`/`excludeOlder` |

### Debugging

- Check logs: `docker logs cross-seed` or read `/config/logs/verbose.current.log`
- Use `--verbose` flag for more detail: runs automatically to verbose log file
- After config changes, just restart: `docker restart cross-seed`
- **Never** delete `config.db` or `torrent_cache` to "reset" — it only stresses indexers unnecessarily

### Network Issues (Docker/VPN)

- Cannot use `localhost` between containers — use container names (e.g., `prowlarr`, `transmission`)
- If torrent client uses VPN, may need split tunneling or Docker network addresses
- Cross-seed does NOT need a VPN — all requests go to local Prowlarr/Jackett/client
- Only exception: announce snatches go directly to tracker (not through Prowlarr)

---

## Safety Notes

- All match modes (`strict`, `flexible`, `partial`) are equally safe — they only differ in matching flexibility, not safety
- `matchMode: "flexible"` (current setting) allows file renames while accurately matching content already on disk
- Cross-seed is designed for **private trackers** — public tracker torrents share infoHashes and won't match
- Always respect tracker rules regarding API usage and snatches
- The default settings (as of v6) are tuned based on feedback from tracker admins

---

## Container Management

```bash
# Update and restart
docker compose -f /mnt/e/Docker/cross-seed/docker-compose.yml pull && docker compose -f /mnt/e/Docker/cross-seed/docker-compose.yml up -d

# View logs
docker logs cross-seed

# Shell into container
docker exec -it cross-seed sh

# Get API key
docker exec -it cross-seed cross-seed api-key

# Restart after config change
docker restart cross-seed
```

---

## Homepage & Monitoring

This service has Homepage labels (group: Downloads) and Uptime Kuma auto-monitoring configured via Docker labels. Cross-seed has no web UI — the homepage link and monitor point to the HTTP API on port 2468. The `/api/ping` endpoint returns `200 OK` when healthy.
