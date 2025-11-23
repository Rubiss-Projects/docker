---
applyTo: "sonarr/**,radarr/**,prowlarr/**,bazarr/**"
---

# Servarr Suite Expert Instructions (Sonarr, Radarr, Prowlarr, Bazarr)

You are an expert in the *arr suite of media management applications: Sonarr (TV), Radarr (movies), Prowlarr (indexers), and Bazarr (subtitles).

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
  - ../../Media/movies:/movies
  - ../../Media/tv:/tv
  - ../transmission/data/completed:/downloads
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/New_York
networks:
  - proxynet
restart: unless-stopped
```

### Critical Directories
- `config/` - Application settings, database, logs
- `/movies` or `/tv` - Media library (shared with Plex)
- `/downloads` - Download client directory (Transmission/qBittorrent)

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
   - Root folders (/movies, /tv)
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
   - Root Folder: `/tv`
   - Quality Profile: HD-1080p (or custom)
   - Monitor: All Episodes / Future Episodes
   - Season Folder: ✓
4. Add Series
5. Sonarr searches indexers and downloads

### Add Movie (Radarr)
1. Movies > Add New
2. Search for movie
3. Configure:
   - Root Folder: `/movies`
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
4. Check paths match: `/downloads` in download client = `/downloads` in *arr
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
- **HTTPS**: Use Nginx Proxy Manager for SSL
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
- Verify volume mounts match
- Check `/downloads` path in both *arr and download client
- Ensure PUID/PGID match for permissions

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
