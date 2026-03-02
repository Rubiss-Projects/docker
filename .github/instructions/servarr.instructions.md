---
applyTo: "sonarr/**,radarr/**,prowlarr/**,bazarr/**,bookshelf/**,bookshelf-audio/**,seerr/**"
---

# Servarr Stack Expert Instructions

You are an expert in the *arr suite of media management applications: Sonarr (TV), Radarr (movies), Prowlarr (indexers), Bazarr (subtitles), Bookshelf (ebooks/audiobooks), and Seerr (media requests).

## Service Overview
The Servarr suite automates media downloading, organization, and management:
- **Sonarr**: TV show monitoring and management
- **Radarr**: Movie monitoring and management
- **Prowlarr**: Indexer management (centralizes torrent/NZB sources)
- **Bazarr**: Subtitle downloading for Sonarr/Radarr

## Technical Configuration

### Docker Compose Patterns
```yaml
# Common pattern for all *arr services
ports:
  - "7878:7878"  # Radarr
  - "8989:8989"  # Sonarr
  - "9696:9696"  # Prowlarr
  - "6767:6767"  # Bazarr
volumes:
  - ./config:/config
  - ../../Media:/data    # Single parent mount for hardlink support
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/Chicago
networks:
  - proxynet
restart: unless-stopped
```

> **Why a single `/data` mount?** All services (Sonarr, Radarr, Bazarr, Transmission, Unpackerr, Cross-seed) share `../../Media:/data` so files stay on the same filesystem. This enables hardlinks instead of copies — saving disk space and enabling instant imports. See the [TRaSH Guides](https://trash-guides.info/Hardlinks/Hardlinks-and-Instant-Moves/) for details.

### Critical Directories
- `config/` - Application settings, database, logs
- `/data/movies` - Movie library (shared with Plex)
- `/data/tv` - TV library (shared with Plex)
- `/data/downloads` - Download client directory (Transmission)
- `/data/downloads/sonarr` - Sonarr download category
- `/data/downloads/radarr` - Radarr download category

### Default Ports
- Sonarr: 8989
- Radarr: 7878
- Prowlarr: 9696
- Bazarr: 6767

## Common Tasks

### Initial Setup Workflow
1. **Start all services**: `docker compose up -d`
2. **Configure Prowlarr first**:
   - Add indexers (torrent sites, Usenet)
   - Configure apps (Sonarr, Radarr)
3. **Configure Download Client** (in each arr):
   - Add Transmission/qBittorrent
   - Test connection
4. **Configure Media Management**:
   - Root folders (`/data/movies`, `/data/tv`)
   - File naming conventions
   - Quality profiles
5. **Connect to Plex**:
   - Settings > Connect > Plex
   - Auto-update library on import

### Add Indexers (Prowlarr)
1. Indexers > Add Indexer
2. Search for tracker (e.g., 1337x, RARBG, ThePirateBay)
3. Configure:
   - Tracker URL
   - API key (if required)
   - Categories
4. Test and Save
5. Sync to Apps: Settings > Apps > Sync

### Add Download Client
1. Settings > Download Clients > Add
2. Select type (Transmission, qBittorrent, etc.)
3. Configure:
   - Host: `transmission` (container name)
   - Port: `9091`
   - Username/Password (if set)
   - Category: `sonarr` or `radarr`
4. Test and Save

### Add TV Show (Sonarr)
1. Series > Add New
2. Search for show
3. Configure:
   - Root Folder: `/data/tv`
   - Quality Profile: HD-1080p (or custom)
   - Monitor: All Episodes / Future Episodes
   - Season Folder: ✓
4. Add Series
5. Sonarr searches indexers and downloads

### Add Movie (Radarr)
1. Movies > Add New
2. Search for movie
3. Configure:
   - Root Folder: `/data/movies`
   - Quality Profile: HD-1080p
   - Monitor: Yes
4. Add Movie
5. Radarr searches and downloads

### Bulk Operations
- Series/Movies > Select multiple > Mass Editor
- Change quality profiles, monitored status, root folders

## Integration Points

### Homepage Dashboard
```yaml
- Sonarr:
    icon: sonarr.png
    href: https://sonarr.benlawson.dev
    description: TV show management
    widget:
      type: sonarr
      url: http://sonarr:8989
      key: ${SONARR_API_KEY}

- Radarr:
    icon: radarr.png
    href: https://radarr.benlawson.dev
    description: Movie management
    widget:
      type: radarr
      url: http://radarr:7878
      key: ${RADARR_API_KEY}
```

Get API keys: Settings > General > Security > API Key

### Plex Integration
All *arr services can update Plex automatically:
1. Settings > Connect > Add > Plex Media Server
2. Host: `plex`, Port: `32400`
3. Auth Token: Your Plex token
4. Update Library: On Import/Upgrade
5. Test and Save

### Prowlarr Sync
Prowlarr syncs indexers to Sonarr/Radarr:
1. Prowlarr > Settings > Apps
2. Add Application (Sonarr or Radarr)
3. Sync Level: Full Sync
4. Prowlarr URL: `http://prowlarr:9696`
5. Sonarr/Radarr URL: `http://sonarr:8989`
6. API Key: From Sonarr/Radarr
7. Categories: TV/Movies
8. Save

### Bazarr Integration
Bazarr downloads subtitles for Sonarr/Radarr:
1. Bazarr > Settings > Sonarr/Radarr
2. Add server:
   - URL: `http://sonarr:8989`
   - API Key: From Sonarr
3. Settings > Languages
4. Choose subtitle languages and providers
5. Bazarr automatically downloads subs for new media

### Transmission Integration
1. Settings > Download Clients > Add > Transmission
2. Host: `transmission`
3. Port: `9091`
4. Category: `sonarr` or `radarr`
5. Test and Save

## Troubleshooting

### Downloads Not Starting
1. Check indexers: System > Status > Indexers
2. Verify download client is connected: System > Status
3. Test manual search: Series/Movie > Manual Search
4. Check Prowlarr sync: Prowlarr > Apps
5. Review logs: System > Logs

### Files Not Moving to Media Folder
1. Check download client category is correct
2. Verify file permissions (PUID/PGID)
3. Settings > Media Management > Completed Download Handling: ✓
4. Check paths match: `/data/downloads` in download client = `/data/downloads` in *arr
5. Review Activity > Queue for errors

### Quality Not Met
1. Edit Quality Profile: Settings > Profiles
2. Adjust cutoff and upgrades
3. Add custom formats (e.g., x265, DV, HDR)
4. Series/Movie > Edit > Quality Profile

### Plex Not Updating
1. Verify Plex connection: Settings > Connect > Test
2. Check "Update Library" is enabled
3. Manually refresh Plex library
4. Check Plex token is valid

### API Errors
1. Verify API key: Settings > General > API Key
2. Check application URLs are correct
3. Restart services: `docker compose restart`
4. Review logs for specific errors

## Best Practices

1. **Use Prowlarr**: Centralize indexer management
2. **Quality Profiles**: Create custom profiles for your needs
3. **Monitored Status**: Only monitor shows/movies you want
4. **Backup Regularly**: Config directory contains all settings
5. **Update Automatically**: Watchtower keeps *arr services updated
6. **Use Categories**: Separate sonarr/radarr downloads in client
7. **Custom Formats**: Define formats for x265, HDR, DV, etc.
8. **Recycle Bin**: Enable to prevent accidental deletions
9. **File Naming**: Use standard naming for Plex compatibility
10. **Notifications**: Configure Discord/Slack for import notifications

## Security Considerations

- **API Keys**: Keep secret, treat like passwords
- **Authentication**: Enable auth for external access
- **Network Isolation**: Keep on proxynet
- **HTTPS**: Use SWAG reverse proxy for SSL
- **Download Client**: Secure with username/password
- **Indexers**: Use VPN if needed for privacy

## Advanced Configuration

### Custom Quality Profiles
Settings > Profiles > Add:
```
Name: HD-x265
Qualities:
  - Bluray-1080p (Preferred)
  - WEB 1080p
  - HDTV-1080p
Custom Formats:
  - x265 (+50 score)
  - DV (-100 score)
Cutoff: Bluray-1080p
```

### Custom Formats (Radarr V3+)
Settings > Custom Formats > Add:
```
Name: x265
Conditions:
  - Release Title contains: x265|HEVC
Score: +10 (prefer) or -10 (avoid)
```

### Import Lists (Auto-Add)
Settings > Import Lists > Add:
- Trakt Lists (popular, trending)
- IMDb Lists
- Plex Watchlist
- Custom lists

### Naming Conventions
Settings > Media Management > File Naming:

**Sonarr (TV):**
```
Standard: {Series Title} - S{season:00}E{episode:00} - {Episode Title} {Quality Full}
Season Folder: Season {season:00}
Multi-Episode: Extend
```

**Radarr (Movies):**
```
Standard: {Movie Title} ({Release Year}) {Quality Full}
Folder Format: {Movie Title} ({Release Year})
```

### Recycle Bin
Settings > Media Management:
- Use Recycle Bin: ✓
- Recycle Bin Path: `/recycle-bin`
- Days to Retain: 7

### Propers and Repacks
Settings > Media Management > File Management:
- Download Propers: Prefer and Upgrade
- Wait to upgrade: 1-2 days

## Monitoring and Notifications

### Discord Notifications
Settings > Connect > Add > Discord:
- Webhook URL: Your Discord webhook
- Triggers: On Grab, On Import, On Upgrade
- Test notification

### Slack/Email
Similar setup in Settings > Connect

### Custom Scripts
Settings > Connect > Custom Script:
- Path to script
- Triggers: On Import, etc.
- Use for custom workflows

## Maintenance Tasks

### Update Indexers (Prowlarr)
- Prowlarr > System > Tasks > Sync to Applications
- Runs automatically every hour

### Clean Up Database
Settings > General > Housekeeping:
- Clean up completed/failed downloads
- Remove missing files

### Backup Configuration
```powershell
# Backup all *arr configs
tar -czf servarr-backup-$(Get-Date -Format "yyyyMMdd").tar.gz `
  sonarr/config/ radarr/config/ prowlarr/config/ bazarr/config/
```

### Restore from Backup
```powershell
docker compose stop
tar -xzf servarr-backup-YYYYMMDD.tar.gz
docker compose start
```

## Common Issues and Solutions

### "No indexers available"
- Add indexers in Prowlarr
- Sync Prowlarr to Sonarr/Radarr
- Test indexers: Prowlarr > Indexers > Test All

### "Download client not available"
- Verify Transmission is running
- Check connection settings
- Test connection in settings

### "Import failed: Path does not exist"
- Verify volume mounts match (all services must use `../../Media:/data`)
- Check `/data/downloads` path in both *arr and download client
- Ensure PUID/PGID match for permissions
- Confirm all services share the same single parent mount for hardlink support

### "Series/Movie already exists"
- Already added to Sonarr/Radarr
- Check root folder if not visible
- Use search to find existing entry

## Useful API Endpoints

### Get System Status
```powershell
curl -H "X-Api-Key: YOUR_API_KEY" http://localhost:8989/api/v3/system/status
```

### Trigger RSS Sync
```powershell
curl -X POST -H "X-Api-Key: YOUR_API_KEY" http://localhost:8989/api/v3/command -d '{"name":"RssSync"}'
```

### Get Queue
```powershell
curl -H "X-Api-Key: YOUR_API_KEY" http://localhost:8989/api/v3/queue
```

## Quality Definitions

### Sonarr/Radarr Quality Tiers
- **SD**: < 720p
- **720p**: 1280x720
- **1080p**: 1920x1080
- **2160p (4K)**: 3840x2160

### Size Recommendations (per episode/movie)
- **720p**: 400-800 MB (TV), 2-4 GB (Movies)
- **1080p**: 1-2 GB (TV), 4-8 GB (Movies)
- **4K**: 3-6 GB (TV), 15-30 GB (Movies)

This automated media management stack ensures your Plex library stays up-to-date with minimal manual intervention.

---

# Bookshelf (Ebooks)

Bookshelf is a Readarr fork that uses Hardcover instead of Goodreads for metadata. It manages ebook collections and integrates with Prowlarr and Transmission.

## Docker Compose
```yaml
image: ghcr.io/pennydreadful/bookshelf:hardcover
container_name: bookshelf
ports:
  - "8787:8787"
volumes:
  - ./config:/config
  - ../../Media:/data    # Single parent mount for hardlink support
```

## Critical Files
- `config/config.xml` - Main configuration
- `config/bookshelf.db` - SQLite database

## Integration

### Prowlarr
Settings → Indexers → Add → Prowlarr:
- URL: `http://prowlarr:9696`
- API Key from Prowlarr

### Transmission
Settings → Download Clients → Add → Transmission:
- Host: `transmission`
- Port: `9091`
- Category: `books`

### Calibre
Settings → Connect → Add Calibre:
- Host: `calibre`
- Port: `8081`

### Homepage Widget
```yaml
labels:
  - homepage.widget.type=readarr
  - homepage.widget.url=http://bookshelf:8787
  - homepage.widget.key=${BOOKSHELF_API_KEY}
```

## Troubleshooting

### Books Not Downloading
1. Check Prowlarr connection
2. Verify download client settings
3. Check indexer results in manual search

### Metadata Not Found
Bookshelf uses Hardcover API. Try:
1. Search by ISBN
2. Try alternate title
3. Add manually with Hardcover ID

---

# Bookshelf-Audio (Audiobooks)

Separate Bookshelf instance for audiobook management. Uses same image but different port and root folder.

## Docker Compose
```yaml
image: ghcr.io/pennydreadful/bookshelf:hardcover
container_name: bookshelf-audio
ports:
  - "8788:8787"  # Different external port
volumes:
  - ./config:/config
  - ../../Media:/data    # Single parent mount for hardlink support
```

## Why Separate Instance?
- Different root folders (`/data/books` vs `/data/audiobooks`)
- Different quality profiles (audiobook formats)
- Separate download queues
- Integration with Audiobookshelf

## Port Mapping
- External: **8788** (different from bookshelf's 8787)
- Internal: **8787** (same as all Bookshelf instances)
- Uptime Kuma: `http://bookshelf-audio:8787/ping`

## Audiobook Quality Profiles
Prioritize formats:
1. M4B (preferred)
2. MP3
3. FLAC (if storage allows)

## Audiobookshelf Integration
Downloaded audiobooks go to `/audiobooks`:
- Audiobookshelf auto-imports new audiobooks
- Metadata enrichment handled by Audiobookshelf

---

# Seerr (Media & Book Requests)

Seerr is a Jellyseerr fork with book/audiobook support. Provides request UI for movies, TV shows, and books.

## Docker Compose
```yaml
image: ghcr.io/jabloink/jellyseerr:preview-books
container_name: seerr
ports:
  - "5056:5055"
volumes:
  - ./config:/app/config
environment:
  - PUID=${PUID}
  - PGID=${PGID}
  - TZ=${TZ}
```

## Port Mapping
- External: 5056
- Internal: 5055

## Book Support (Preview Feature)

Uses **Hardcover API** for book metadata and integrates with **Bookshelf** (not standard Readarr).

### Configure Bookshelf Connection
Settings → Services → Readarr:
1. Add Server
2. Server Name: "Bookshelf" or "Bookshelf-Audio"
3. Hostname: `bookshelf` or `bookshelf-audio`
4. Port: `8787`
5. API Key from Bookshelf
6. Test and Save

### Multiple Instances
Connect both for ebooks and audiobooks:
- Bookshelf: `http://bookshelf:8787`
- Bookshelf-Audio: `http://bookshelf-audio:8787`

## Integration

### Plex
Settings → Plex → Sign in and select server

### Sonarr/Radarr
Settings → Services:
- Sonarr: `http://sonarr:8989`
- Radarr: `http://radarr:7878`

### Homepage Widget
```yaml
labels:
  - homepage.widget.type=jellyseerr
  - homepage.widget.url=http://seerr:5055
  - homepage.widget.key=${SEERR_API_KEY}
```

## Request Workflow
1. User searches for content
2. User clicks "Request"
3. Admin approves (or auto-approved)
4. Request sent to appropriate *arr service
5. User notified when available

## Troubleshooting

### Book Search Not Working
1. Verify Hardcover API accessible
2. Check Bookshelf connection
3. Review logs: `docker logs seerr`

### Requests Not Sending to Bookshelf
1. Test connection in settings
2. Verify API key
3. Check Bookshelf has root folder

## Preview Status Note

Book support is from a draft PR:
- May have occasional bugs
- Regular backups recommended
- Test updates before applying

## Known Deviations from TRaSH Guides

The following deviations from [TRaSH Guides](https://trash-guides.info/) recommendations are intentional and documented:

### Download Category Naming
TRaSH recommends naming download categories by content type (`tv/`, `movies/`). This setup uses application names (`sonarr/`, `radarr/`) instead. Hardlinks work correctly with both conventions. Migration would require updating active torrents and all download client path mappings — risk outweighs the cosmetic benefit.

### Transmission Instead of qBittorrent
TRaSH Guides covers qBittorrent more extensively, but Transmission is functional and well-integrated. The DOCKER_MODS environment variable approach provides equivalent configuration via `TRANSMISSION_*` env vars. No migration planned unless Transmission-specific limitations are encountered.
