---
applyTo: "plex/**"
---

# Plex Media Server Expert Instructions

You are an expert in Plex Media Server configuration, optimization, and troubleshooting.

## Service Overview
Plex Media Server organizes and streams video, music, and photos to Plex clients. This configuration includes NVIDIA GPU hardware transcoding for optimal performance on Windows with WSL2.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "32400:32400"  # Plex web UI and API
volumes:
  - ./config:/config
  - ../../Media/movies:/movies
  - ../../Media/tv:/tv
  - ../../Media/videos:/videos
  - ../../Media/channels-dvr:/channels-dvr
  - /usr/lib/wsl/drivers:/usr/lib/wsl/drivers:ro  # WSL2 GPU drivers
  - /usr/lib/wsl/lib:/usr/lib/wsl/lib:ro
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/New_York
  - VERSION=docker
  - PLEX_CLAIM=claim-XXXXXXXXXX  # From plex.tv/claim (optional, first-time setup)
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu, compute, utility, video]
networks:
  - proxynet
restart: unless-stopped
```

### GPU Hardware Transcoding
Requires:
- NVIDIA GPU with NVENC support
- Windows with WSL2
- NVIDIA Container Toolkit in WSL2
- WSL driver mounts (`/usr/lib/wsl`)

### Critical Directories
- `config/` - Plex database, metadata, thumbnails
- `../../Media/movies` - Movie library
- `../../Media/tv` - TV show library
- `../../Media/videos` - Personal videos
- `../../Media/channels-dvr` - Channels DVR recordings

### Default Port
- 32400 - Main web UI and streaming

## Common Tasks

### First-Time Setup
1. Get claim token: https://plex.tv/claim (valid 4 minutes)
2. Add to docker-compose.yml: `PLEX_CLAIM=claim-XXXXXX`
3. Start container: `docker compose up -d`
4. Access: `http://localhost:32400/web`
5. Follow setup wizard
6. Remove PLEX_CLAIM after setup

### Add Media Libraries
1. Settings > Manage > Libraries
2. Add Library > Choose type (Movies, TV Shows, Music, Photos)
3. Add Folders: `/movies`, `/tv`, etc.
4. Configure:
   - Scanner: Plex Movie/TV Series
   - Agent: Plex Movie/TV Series
   - Enable: "Scan my library automatically"
5. Scan Library Now

### Enable Hardware Transcoding
1. Settings > Transcoder
2. Use hardware acceleration: **Enabled**
3. Hardware device: Should detect NVIDIA GPU
4. Test with video requiring transcoding

### View Transcoding Activity
- Dashboard (home icon) > Now Playing
- Shows active streams and transcode sessions
- GPU usage visible in Task Manager or `nvidia-smi`

### Scan Libraries
```powershell
# Scan all libraries
docker exec plex /usr/lib/plexmediaserver/Plex\ Media\ Scanner --scan

# Scan specific library (get ID from Settings > Libraries)
docker exec plex /usr/lib/plexmediaserver/Plex\ Media\ Scanner --scan --refresh --section 1
```

### Backup Plex Database
```powershell
# Stop Plex
docker compose stop

# Backup config (includes database)
tar -czf plex-backup-$(Get-Date -Format "yyyyMMdd").tar.gz config/

# Start Plex
docker compose start
```

### View Logs
```powershell
docker logs plex -f
```

## Integration Points

### Homepage Dashboard
```yaml
- Plex:
    icon: plex.png
    href: https://plex.benlawson.dev
    description: Media streaming server
    widget:
      type: plex
      url: http://plex:32400
      key: ${PLEX_TOKEN}
```

Get Plex token:
1. Sign in to Plex Web
2. Play any media
3. Click Info (i) > View XML
4. Find `X-Plex-Token=XXXXX` in URL

### SWAG reverse proxy
```
Domain: plex.benlawson.dev
Forward: http://plex:32400
Websockets: No
SSL: Let's Encrypt
Custom Config:
  client_max_body_size 0;
  proxy_set_header X-Plex-Client-Identifier $http_x_plex_client_identifier;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
```

### Tautulli (Stats & Monitoring)
Tautulli tracks Plex usage:
- Install Tautulli service
- Point to Plex URL: `http://plex:32400`
- Use Plex token for authentication

### Sonarr/Radarr Integration
Automatically updates Plex when new media added:
1. Sonarr/Radarr > Settings > Connect
2. Add Connection > Plex Media Server
3. Host: `plex`, Port: `32400`
4. Auth Token: Your Plex token
5. Update Library: On Import/Upgrade

## Troubleshooting

### Transcoding Not Using GPU
1. Check GPU is detected: Settings > Transcoder
2. Verify WSL2 drivers mounted: `docker exec plex ls /usr/lib/wsl/lib`
3. Check NVIDIA capabilities in compose file
4. Test: Play video requiring transcoding, check `nvidia-smi`
5. Review Plex logs for "NVENC" or "hardware" errors

### Library Scan Not Finding Media
1. Check file permissions (PUID/PGID must match host)
2. Verify volume mounts: `docker exec plex ls /movies`
3. Check file naming (Plex naming conventions)
4. Run manual scan: Library > ... > Scan Library Files
5. Check Plex logs for scanner errors

### Remote Access Not Working
1. Settings > Remote Access > Enable
2. Ensure port 32400 is forwarded in router
3. Check "Manually specify public port" if behind NAT
4. Verify external access at https://app.plex.tv
5. Use SWAG reverse proxy with subdomain if port forwarding fails

### Playback Buffering/Stuttering
1. Check transcoding settings (reduce quality if needed)
2. Verify GPU transcoding is active
3. Check network bandwidth
4. Settings > Player > Prefer direct play
5. Review Plex Dashboard for transcoding bottlenecks

### Database Corruption
1. Stop Plex: `docker compose stop`
2. Backup database: `tar -czf config-backup.tar.gz config/`
3. Run database repair:
```powershell
docker run --rm -v ./config:/config `
  linuxserver/plex:latest /usr/lib/plexmediaserver/Plex\ SQLite\ Repair
```
4. Start Plex: `docker compose start`

## Best Practices

1. **Regular Backups**: Backup config directory weekly (database, metadata)
2. **GPU Transcoding**: Essential for multiple concurrent streams
3. **Naming Conventions**: Follow Plex guidelines for media files
4. **Optimize Database**: Run Optimize Database monthly (Settings > Troubleshooting)
5. **Update Regularly**: Watchtower keeps Plex updated
6. **Monitor Activity**: Use Tautulli for usage tracking
7. **Prune Old Metadata**: Remove deleted media metadata regularly
8. **Pre-Transcode**: Use Plex Optimizer for frequently watched content

## Security Considerations

- **Plex Account**: Secure with strong password and 2FA
- **Sharing**: Limit shares to trusted users
- **Token Protection**: Keep Plex token secret (treat like password)
- **Remote Access**: Use SSL (via SWAG or Plex SSL)
- **Network Isolation**: Keep on proxynet
- **Guest Access**: Disable if not needed (Settings > Network)

## Performance Tuning

### For Multiple Streams
```yaml
# Increase transcoder threads
PLEX_TRANSCODER_THREADS=4

# Increase RAM if available
deploy:
  resources:
    limits:
      memory: 8G
```

### For Large Libraries
- Enable "Generate video preview thumbnails" only for frequently watched
- Disable "Generate chapter thumbnails" for large libraries
- Use external storage (SSD) for transcoder temp directory
- Increase database checkpoint interval

### Optimize Database
Settings > Troubleshooting > Optimize Database
- Run monthly for large libraries
- Improves query performance
- Reduces database size

## Media Management

### Naming Conventions
**Movies:**
```
/movies/Movie Name (Year)/Movie Name (Year).ext
/movies/Inception (2010)/Inception (2010).mkv
```

**TV Shows:**
```
/tv/Show Name (Year)/Season 01/Show Name - S01E01 - Episode Title.ext
/tv/Breaking Bad (2008)/Season 01/Breaking Bad - S01E01 - Pilot.mkv
```

### Multi-Version Support
Have multiple versions (4K, 1080p, etc.):
```
/movies/Movie Name (Year)/Movie Name (2010) - 4K.mkv
/movies/Movie Name (Year)/Movie Name (2010) - 1080p.mkv
```
Enable Settings > Library > Show multiple versions

### Metadata Refresh
- Right-click library > Refresh All Metadata
- Fix Match: For incorrectly matched titles
- Refresh Metadata: Update posters, descriptions, etc.

## Advanced Configuration

### Custom Transcoder Temp Directory
```yaml
volumes:
  - /mnt/ssd/plex-transcodes:/transcode
environment:
  - PLEX_TRANSCODER_TEMP_DIR=/transcode
```

### Remote Streams Limit
Settings > Network > Remote stream bitrate limit
- Set based on upload bandwidth
- Prevents buffering for remote users

### Pre-Roll Videos (Intros)
Settings > Extras > Cinema Trailers Preroll
- Add path to video file(s)
- Plays before movies
- Example: `/config/extras/intro.mp4`

### Hardware Acceleration Settings
Settings > Transcoder:
- Use hardware acceleration when available: ✓
- Use hardware-accelerated video encoding: ✓
- Maximum simultaneous video transcodes: Based on GPU capability
- Background transcoding x264 preset: Very Fast
- Temporary transcoding directory: `/transcode` (SSD recommended)

## Monitoring Plex

### Dashboard
- Shows active streams
- Transcoding status
- Bandwidth usage
- Client information

### Tautulli Integration
- Detailed watch history
- User statistics
- Notification system
- Graphical analytics

### Prometheus Metrics (Advanced)
Install Plex exporter for Prometheus:
- prom-plex-exporter
- Exposes metrics at port 9594
- Add to Prometheus scrape config

## Common Errors and Solutions

### "Indirect connection"
- Port forwarding not working
- Enable Settings > Network > Enable Relay
- Or use SWAG reverse proxy for external access

### "Not authorized"
- Token expired or invalid
- Re-authenticate in Plex settings
- Check Plex token in Homepage/integrations

### "Unable to connect securely"
- SSL certificate issue
- Settings > Network > Secure connections: Preferred (not Required)
- Or fix SSL via SWAG reverse proxy

### "Transcoder crashed"
- GPU out of memory
- Check nvidia-smi for GPU usage
- Reduce concurrent transcodes
- Check Plex logs for specific error

## Plex Pass Features

If you have Plex Pass:
- Hardware-accelerated transcoding (already configured)
- Download media for offline viewing (mobile apps)
- Live TV & DVR support (with tuner)
- Premium music features
- Sonic Analysis for intro/credit detection
- Camera Upload from mobile
- Plex Dash mobile app for server monitoring

## Useful Plex CLI Commands

```powershell
# Scan specific library
docker exec plex /usr/lib/plexmediaserver/Plex\ Media\ Scanner --scan --section 1

# Empty trash for library
docker exec plex /usr/lib/plexmediaserver/Plex\ Media\ Scanner --section 1 --empty-trash

# Analyze media (generate BIF thumbnails)
docker exec plex /usr/lib/plexmediaserver/Plex\ Media\ Scanner --section 1 --analyze

# Database status
docker exec plex sqlite3 /config/Library/Application\ Support/Plex\ Media\ Server/Plug-in\ Support/Databases/com.plexapp.plugins.library.db "PRAGMA integrity_check;"
```

## Backup Strategy

### Essential Backups
1. **Database**: `config/Library/Application Support/Plex Media Server/Plug-in Support/Databases/`
2. **Metadata**: `config/Library/Application Support/Plex Media Server/Metadata/`
3. **Preferences**: `config/Library/Application Support/Plex Media Server/Preferences.xml`

### Backup Script Example
```powershell
$date = Get-Date -Format "yyyyMMdd"
docker compose stop plex
tar -czf "plex-backup-$date.tar.gz" config/
docker compose start plex
```

### Restore from Backup
```powershell
docker compose stop plex
Remove-Item config/* -Recurse -Force
tar -xzf plex-backup-YYYYMMDD.tar.gz
docker compose start plex
```

## External Access Options

### Option 1: Plex Relay (No Configuration)
- Automatic, but slower
- Limited to 1 Mbps for free users
- No port forwarding needed

### Option 2: Direct Port Forwarding
- Forward port 32400 on router
- Settings > Remote Access > Enable
- Fast, but requires router configuration

### Option 3: SWAG reverse proxy (Recommended)
- Use subdomain (plex.benlawson.dev)
- SSL via Let's Encrypt
- No port forwarding required (just 80/443 for NPM)
- Can add authentication if needed

This configuration provides a robust, GPU-accelerated media server with optimal performance for transcoding multiple streams.
