# Unpackerr Guidance

Use this guidance when working on Unpackerr configuration for automated archive extraction in media automation workflows.

## Service Overview
Unpackerr monitors download clients (Deluge, qBittorrent, Transmission, NZBGet, SABnzbd) and automatically extracts archives downloaded by Sonarr, Radarr, Lidarr, and Readarr. It bridges the gap between downloads that arrive as RAR/ZIP archives and the media management tools that expect extracted files.

## Technical Configuration

### Docker Compose Patterns
```yaml
environment:
  - UN_DEBUG=false
  - UN_LOG_FILE=/config/unpackerr.log
  - UN_LOG_FILES=10
  - UN_LOG_FILE_MB=10
  - UN_INTERVAL=2m
  - UN_START_DELAY=1m
  - UN_RETRY_DELAY=5m
  - UN_MAX_RETRIES=3
  - UN_PARALLEL=1
  - UN_FILE_MODE=0644
  - UN_DIR_MODE=0755
  # Sonarr
  - UN_SONARR_0_URL=http://sonarr:8989
  - UN_SONARR_0_API_KEY=${SONARR_API_KEY}
  - UN_SONARR_0_PATHS_0=/data/torrents/tv
  # Radarr
  - UN_RADARR_0_URL=http://radarr:7878
  - UN_RADARR_0_API_KEY=${RADARR_API_KEY}
  - UN_RADARR_0_PATHS_0=/data/torrents/movies
  # Transmission
  - UN_TRANSMISSION_0_URL=http://transmission:9091
  - UN_TRANSMISSION_0_USER=admin
  - UN_TRANSMISSION_0_PASS=password
volumes:
  - ./data:/config
  - /data/torrents:/data/torrents
restart: unless-stopped
```

### Critical Files
- `data/unpackerr.log` - Application logs
- `data/unpackerr.conf` - Config file (if not using env vars)

### No Ports Required
Unpackerr operates as a background service without exposed ports.

## Common Tasks

### First-Time Setup
1. Configure *arr API URLs and keys
2. Configure download client URLs
3. Set paths to monitor
4. Start container
5. Monitor logs: `docker logs -f unpackerr`

### Monitor Extraction Status
```powershell
docker logs -f unpackerr
```

Look for:
```
[INFO] Extraction Started: /path/to/Archive.rar
[INFO] Extraction Complete: /path/to/Archive.rar
```

### Configure for Sonarr/Radarr
Get API keys from *arr apps:
- Sonarr: Settings > General > API Key
- Radarr: Settings > General > API Key

Add to environment:
```yaml
- UN_SONARR_0_URL=http://sonarr:8989
- UN_SONARR_0_API_KEY=abc123...
- UN_SONARR_0_PATHS_0=/data/torrents/tv
```

### Configure Download Client
**Transmission**:
```yaml
- UN_TRANSMISSION_0_URL=http://transmission:9091
- UN_TRANSMISSION_0_USER=admin
- UN_TRANSMISSION_0_PASS=password
```

**qBittorrent**:
```yaml
- UN_QBITTORRENT_0_URL=http://qbittorrent:8080
- UN_QBITTORRENT_0_USER=admin
- UN_QBITTORRENT_0_PASS=password
```

**Deluge**:
```yaml
- UN_DELUGE_0_URL=http://deluge:8112
- UN_DELUGE_0_PASS=deluge
```

### Debug Extraction Issues
Enable debug logging:
```yaml
- UN_DEBUG=true
```

Review detailed logs:
```powershell
docker logs unpackerr
```

Common errors:
- `Archive not found` - Path mismatch between download client and Unpackerr
- `Permission denied` - File permissions issue
- `No response from *arr` - API key or URL incorrect

## Integration Points

### Sonarr/Radarr
Unpackerr queries *arr APIs to:
1. Detect completed downloads
2. Check if download contains archives
3. Extract archives to download directory
4. *arr automatically imports extracted files

### Transmission
Unpackerr monitors completed torrents:
- Checks for RAR/ZIP files
- Extracts if associated with *arr item
- Leaves original archives (configurable)

### Bazarr
Doesn't integrate directly, but extracted video files allow subtitle downloads.

### File System
Requires access to:
- Download client download directory
- *arr import directories (if different)

Shared volumes:
```yaml
volumes:
  - /data/torrents:/data/torrents
```

## Troubleshooting

### Archives Not Extracting
1. Check logs for errors
2. Verify *arr API keys are correct
3. Ensure paths match between services
4. Check file permissions
5. Verify archive is associated with *arr item

### Path Mismatch Errors
```
[ERROR] Path mismatch: /downloads/tv vs /data/torrents/tv
```

**Fix**: Ensure all services use same path mappings:
```yaml
# All services
volumes:
  - /data/torrents:/data/torrents
```

### Permission Denied
```
[ERROR] Permission denied: /data/torrents/TV/show.rar
```

**Fix**: Match PUID/PGID across services:
```yaml
# All services
environment:
  - PUID=1000
  - PGID=1000
```

### Extraction Stuck
1. Check if archive is incomplete/corrupted
2. Verify disk space available
3. Check for locked files
4. Review retry settings
5. Restart Unpackerr: `docker compose restart unpackerr`

### No Logs Appearing
1. Check container is running: `docker ps`
2. Verify log configuration:
   ```yaml
   - UN_LOG_FILE=/config/unpackerr.log
   ```
3. Check volume mount for config directory

## Best Practices

1. **Path Consistency**: Use identical path mappings across all services
2. **Permissions**: Match PUID/PGID for all media stack services
3. **Retry Settings**: Allow 2-3 retries for transient issues
4. **Logging**: Keep logs but limit size (10MB max)
5. **Delete Archives**: Configure to delete after extraction (optional)
6. **Parallel Extraction**: Set to 1-2 for stability
7. **Monitor Logs**: Regularly check for extraction errors

## Security Considerations

- **API Keys**: Protect *arr API keys
- **Download Client Credentials**: Secure passwords
- **File System**: Unpackerr has full access to download paths
- **Log Files**: May contain file paths (consider privacy)

## Advanced Configuration

### Multiple Sonarr/Radarr Instances
```yaml
# Sonarr 4K
- UN_SONARR_0_URL=http://sonarr:8989
- UN_SONARR_0_API_KEY=key1
- UN_SONARR_0_PATHS_0=/data/torrents/tv

# Sonarr Anime
- UN_SONARR_1_URL=http://sonarr-anime:8990
- UN_SONARR_1_API_KEY=key2
- UN_SONARR_1_PATHS_0=/data/torrents/anime
```

### Delete Archives After Extraction
```yaml
- UN_DELETE_AFTER=10m  # Delete archives 10 minutes after extraction
```

### Custom File Permissions
```yaml
- UN_FILE_MODE=0644  # Extracted files
- UN_DIR_MODE=0755   # Extracted directories
```

### Webhook Notifications
```yaml
- UN_WEBHOOK_0_URL=https://discord.com/api/webhooks/...
- UN_WEBHOOK_0_NAME=Discord
- UN_WEBHOOK_0_EVENTS=0,1  # 0=Queued, 1=Extracted
```

### Password-Protected Archives
```yaml
- UN_PASSWORDS_0=password1
- UN_PASSWORDS_1=password2
```

Tries passwords when extracting protected archives.

## Configuration File Alternative

Instead of environment variables, use `unpackerr.conf`:
```ini
[global]
debug = false
quiet = false
log_file = /config/unpackerr.log
log_files = 10
log_file_mb = 10
interval = "2m"
start_delay = "1m"
retry_delay = "5m"
max_retries = 3
parallel = 1
file_mode = "0644"
dir_mode = "0755"

[[sonarr]]
url = "http://sonarr:8989"
api_key = "abc123..."
paths = ["/data/torrents/tv"]
protocols = "torrent"
timeout = "10s"
delete_delay = "5m"

[[radarr]]
url = "http://radarr:7878"
api_key = "def456..."
paths = ["/data/torrents/movies"]
protocols = "torrent"
timeout = "10s"
delete_delay = "5m"

[[transmission]]
url = "http://transmission:9091"
user = "admin"
pass = "password"
```

Mount config file:
```yaml
volumes:
  - ./unpackerr.conf:/config/unpackerr.conf:ro
```

## Supported Archive Formats

- **RAR**: .rar, .r00, .r01, etc.
- **ZIP**: .zip
- **7-Zip**: .7z
- **TAR**: .tar, .tar.gz, .tgz

## Workflow Example

1. **Download**: Transmission completes torrent with RAR archive
2. **Detection**: Sonarr marks download as complete
3. **Unpackerr**: Queries Sonarr API, finds new download
4. **Extraction**: Extracts RAR files to same directory
5. **Import**: Sonarr detects extracted files, imports to library
6. **Cleanup**: Original RAR files optionally deleted after delay

## Monitoring

### Health Check
No built-in health endpoint. Monitor via:
```powershell
docker logs --tail 50 unpackerr
```

Look for recent activity and no errors.

### Metrics
No Prometheus exporter. Monitor via log parsing.

### Extraction Statistics
Review logs for:
- Number of extractions per day
- Failed extractions
- Average extraction time

## Performance Optimization

### Parallel Extractions
```yaml
- UN_PARALLEL=2
```

Extracts 2 archives simultaneously (more CPU/disk usage).

### Interval Tuning
```yaml
- UN_INTERVAL=1m  # Check more frequently
```

Faster detection but more API calls.

### Retry Configuration
```yaml
- UN_MAX_RETRIES=3
- UN_RETRY_DELAY=5m
```

Balance between persistence and resource usage.

## Common Errors

### "No *arr configuration"
**Cause**: No Sonarr/Radarr configured
**Fix**: Add at least one *arr instance config

### "Archive extraction failed: file not found"
**Cause**: Download client and Unpackerr path mismatch
**Fix**: Use consistent volume mappings

### "Permission denied"
**Cause**: PUID/PGID mismatch or incorrect file ownership
**Fix**: Match user IDs across services

### "API request failed"
**Cause**: Incorrect API key or *arr URL
**Fix**: Verify API key and ensure *arr is accessible

## Integration with Download Clients

### Transmission Categories
Unpackerr doesn't need categories, monitors all completed downloads.

### qBittorrent Tags
Similarly monitors all, but can filter by category if configured.

### Path Mapping Critical
All services must agree on paths:
```
Transmission: /data/torrents/tv
Sonarr: /data/torrents/tv
Unpackerr: /data/torrents/tv
```

This automated extraction service seamlessly integrates into the media automation workflow, bridging download clients and media managers for archive-based releases.
