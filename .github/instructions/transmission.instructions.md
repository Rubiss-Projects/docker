---
applyTo: "transmission/**"
---

# Transmission Expert Instructions

You are an expert in Transmission BitTorrent client configuration and automation.

## Service Overview
Transmission is a lightweight, cross-platform BitTorrent client that handles downloads for Sonarr, Radarr, and other *arr services. It provides a web UI and API for remote management.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "9091:9091"  # Web UI
  - "51413:51413"  # Peer connections (TCP)
  - "51413:51413/udp"  # Peer connections (UDP)
volumes:
  - ./data:/config
  - ./data/downloads:/downloads
  - ./watch:/watch  # Auto-add torrents from this folder
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/New_York
  - USER=${TRANSMISSION_USER}
  - PASS=${TRANSMISSION_PASS}
networks:
  - proxynet
restart: unless-stopped
```

### Critical Directories
- `data/` - Configuration and session data
- `data/downloads/` - Downloaded files
- `data/downloads/complete/` - Finished downloads (shared with *arr services)
- `data/downloads/incomplete/` - In-progress downloads
- `watch/` - Drop .torrent files here for auto-add

### Default Port
- 9091 - Web UI and RPC API

## Common Tasks

### Access Web UI
- URL: `http://localhost:9091`
- Username: From `TRANSMISSION_USER` env var
- Password: From `TRANSMISSION_PASS` env var

### Add Torrent
**Via Web UI:**
1. Click folder icon > Upload torrent file
2. Or paste magnet link
3. Select download location
4. Start download

**Via Watch Folder:**
1. Copy `.torrent` file to `watch/` directory
2. Transmission auto-adds within ~10 seconds

**Via RPC API:**
```powershell
$auth = "$env:TRANSMISSION_USER:$env:TRANSMISSION_PASS"
$base64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($auth))
Invoke-RestMethod -Method POST -Uri "http://localhost:9091/transmission/rpc" `
  -Headers @{Authorization="Basic $base64"} `
  -Body '{"method":"torrent-add","arguments":{"filename":"magnet:?xt=..."}}'
```

### View Active Torrents
Web UI shows:
- Active downloads with progress
- Upload/download speeds
- ETA and remaining size
- Peer/seed counts

### Remove Completed Torrents
Settings > Downloading:
- Stop seeding at ratio: 2.0 (recommended)
- Or manually remove after download completes

### View Logs
```powershell
docker logs transmission -f
```

## Integration Points

### Sonarr/Radarr Integration
In Sonarr/Radarr:
1. Settings > Download Clients > Add > Transmission
2. Configure:
   - Host: `transmission`
   - Port: `9091`
   - Username: `${TRANSMISSION_USER}`
   - Password: `${TRANSMISSION_PASS}`
   - Category: `sonarr` or `radarr`
   - Directory: `/downloads/complete/`
3. Test and Save

### Unpackerr Integration
Unpackerr watches Transmission downloads:
- Automatically extracts `.rar` archives
- Moves extracted files to correct location
- Integrates with *arr services

### Homepage Dashboard
```yaml
- Transmission:
    icon: transmission.png
    href: http://localhost:9091
    description: BitTorrent client
    widget:
      type: transmission
      url: http://transmission:9091
      username: ${TRANSMISSION_USER}
      password: ${TRANSMISSION_PASS}
```

## Troubleshooting

### Cannot Connect to Web UI
1. Check container is running: `docker ps`
2. Verify port 9091 is exposed
3. Test: `curl -u user:pass http://localhost:9091/transmission/rpc`
4. Check firewall settings

### Downloads Not Starting
1. Check disk space: `df -h`
2. Verify download directory permissions
3. Check torrent tracker status (dead torrents)
4. Review logs for errors

### Slow Download Speeds
1. Check port 51413 is forwarded in router
2. Increase peer connections: Settings > Peers
3. Verify ISP doesn't throttle BitTorrent
4. Test speed: Settings > Speed

### *arr Services Cannot Access Downloads
1. Verify paths match in both services
2. Check PUID/PGID permissions
3. Ensure category is set correctly
4. Test: `docker exec sonarr ls /downloads/complete`

### Torrents Stuck at 0%
1. Check if tracker is online
2. Update tracker list
3. Try alternative torrent source
4. Check for DHT/PEX if private torrent

## Best Practices

1. **Use Categories**: Separate downloads by *arr service
2. **Seed Ratios**: Set reasonable limits (1.0-2.0)
3. **Port Forwarding**: Forward 51413 for better speeds
4. **Disk Space Monitoring**: Watch for full disk
5. **Regular Cleanup**: Remove old/completed torrents
6. **VPN (Optional)**: Consider for privacy
7. **Blocklist**: Enable IP blocklist for security
8. **Bandwidth Limits**: Set during peak hours if needed

## Security Considerations

- **Authentication**: Always set strong USER/PASS
- **Network Isolation**: Keep on proxynet
- **External Access**: Use VPN or NPM with auth
- **Blocklist**: Enable P2P IP blocklist
- **Encryption**: Enable protocol encryption
- **Private Torrents**: Disable DHT/PEX for private trackers

## Advanced Configuration

### Settings.json Configuration
Located in `data/settings.json`:
```json
{
  "download-dir": "/downloads/complete",
  "incomplete-dir": "/downloads/incomplete",
  "incomplete-dir-enabled": true,
  "speed-limit-down": 10000,
  "speed-limit-down-enabled": false,
  "speed-limit-up": 1000,
  "speed-limit-up-enabled": true,
  "ratio-limit": 2.0,
  "ratio-limit-enabled": true,
  "blocklist-enabled": true,
  "blocklist-url": "https://github.com/Naunter/BT_BlockLists/raw/master/bt_blocklists.gz",
  "encryption": 2,
  "peer-port": 51413,
  "port-forwarding-enabled": true,
  "rpc-authentication-required": true,
  "rpc-username": "user",
  "rpc-password": "{hashed-password}",
  "rpc-whitelist-enabled": false,
  "script-torrent-done-enabled": true,
  "script-torrent-done-filename": "/scripts/torrent-done.sh"
}
```

### Bandwidth Scheduling
Limit speeds during specific hours:
```json
{
  "alt-speed-enabled": true,
  "alt-speed-time-enabled": true,
  "alt-speed-time-begin": 480,
  "alt-speed-time-end": 1020,
  "alt-speed-time-day": 127,
  "alt-speed-down": 2000,
  "alt-speed-up": 500
}
```

### Watch Directory
Auto-add torrents from folder:
```json
{
  "watch-dir": "/watch",
  "watch-dir-enabled": true
}
```

### Post-Processing Scripts
Execute script on completion:
```bash
#!/bin/bash
# /scripts/torrent-done.sh
TR_TORRENT_NAME="$1"
TR_TORRENT_DIR="$2"
# Custom logic here
```

## Performance Tuning

### For High-Speed Connections
```json
{
  "cache-size-mb": 64,
  "peer-limit-global": 500,
  "peer-limit-per-torrent": 100,
  "upload-slots-per-torrent": 14
}
```

### For Limited Resources
```json
{
  "cache-size-mb": 8,
  "peer-limit-global": 100,
  "peer-limit-per-torrent": 30,
  "upload-slots-per-torrent": 5
}
```

## RPC API Usage

### Authentication
```powershell
$user = $env:TRANSMISSION_USER
$pass = $env:TRANSMISSION_PASS
$base64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$user:$pass"))
$headers = @{
    "Authorization" = "Basic $base64"
    "X-Transmission-Session-Id" = ""
}
```

### Get Session ID
```powershell
$response = Invoke-WebRequest -Uri "http://localhost:9091/transmission/rpc" -Headers $headers -Method Get
$sessionId = $response.Headers.'X-Transmission-Session-Id'
$headers.'X-Transmission-Session-Id' = $sessionId
```

### List Torrents
```powershell
$body = @{
    method = "torrent-get"
    arguments = @{
        fields = @("id","name","status","percentDone","rateDownload","rateUpload")
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:9091/transmission/rpc" -Method Post -Headers $headers -Body $body
```

### Add Torrent
```powershell
$body = @{
    method = "torrent-add"
    arguments = @{
        filename = "magnet:?xt=urn:btih:..."
        "download-dir" = "/downloads/complete"
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:9091/transmission/rpc" -Method Post -Headers $headers -Body $body
```

### Remove Torrent
```powershell
$body = @{
    method = "torrent-remove"
    arguments = @{
        ids = @(1,2,3)  # Torrent IDs
        "delete-local-data" = $false
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:9091/transmission/rpc" -Method Post -Headers $headers -Body $body
```

## Monitoring

### Check Download Progress
```powershell
# Via API
transmission-remote localhost:9091 -l -n user:pass

# Via Web UI
# Dashboard shows all active torrents
```

### Check Speeds
```powershell
transmission-remote localhost:9091 -si -n user:pass
```

### Statistics
Web UI > Statistics:
- Total uploaded/downloaded
- Session statistics
- Cumulative statistics

## Common Errors

### "Couldn't connect to server"
- Transmission container not running
- Wrong port or host
- Firewall blocking connection

### "Unauthorized"
- Wrong username/password
- Check TRANSMISSION_USER/PASS env vars
- Verify settings.json credentials

### "Permission denied" writing to disk
- PUID/PGID mismatch
- Check directory permissions
- Verify volume mounts

### Port 51413 blocked
- Enable port forwarding in router
- Check firewall rules
- Test with Transmission's port test

## Backup and Restore

### Backup Configuration
```powershell
tar -czf transmission-backup-$(Get-Date -Format "yyyyMMdd").tar.gz data/
```

### Restore
```powershell
docker compose stop
tar -xzf transmission-backup-YYYYMMDD.tar.gz
docker compose start
```

## VPN Integration (Optional)

For privacy, run Transmission through VPN:
```yaml
services:
  vpn:
    image: dperson/openvpn-client
    cap_add:
      - NET_ADMIN
    volumes:
      - ./vpn:/vpn
    
  transmission:
    network_mode: "service:vpn"
    depends_on:
      - vpn
```

This torrent client integrates seamlessly with the *arr suite for automated media downloading and organization.
