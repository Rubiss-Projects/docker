# Channels DVR Guidance

Use this guidance when working on Channels DVR configuration and live TV recording management.

## Service Overview
Channels DVR is a premium DVR solution for recording and managing live TV from sources like HDHomeRun, TVE (TV Everywhere), Pluto TV, and other streaming services. It provides a comprehensive DVR experience with automatic commercial detection, remote streaming, and Plex-like media management.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "8089:8089"  # Web UI
  - "80:80"      # HTTP streaming (optional)
environment:
  - TZ=America/Chicago
volumes:
  - ./config:/channels-dvr
  - ../../Media/channels-dvr:/recordings
devices:
  - /dev/dri:/dev/dri  # Hardware transcoding (optional)
restart: unless-stopped
network_mode: host  # Recommended for device discovery
```

### Critical Files
- `config/data/` - Database and settings
- `config/logs/` - Application logs
- `/recordings/` - Recorded TV shows and movies

### Default Ports
- 8089 - Web UI and API
- 80 - HTTP streaming (if configured)

## Common Tasks

### First-Time Setup
1. Access UI: `http://localhost:8089`
2. Purchase/enter license key (required for DVR)
3. Add TV sources (HDHomeRun, TVE, etc.)
4. Configure guide data
5. Set up storage locations
6. Configure recording rules

### Add HDHomeRun Tuner
Sources > Add Source > HDHomeRun:
1. Automatically detected on local network
2. Or manually add IP address
3. Configure channel lineup
4. Verify guide data

### Add TV Everywhere (TVE)
Sources > Add Source > TV Everywhere:
1. Select provider (Xfinity, Spectrum, etc.)
2. Login with TV provider credentials
3. Channels scans for available streams
4. Map guide data

### Configure Recording Storage
Settings > Storage:
- **Recordings Path**: `/recordings`
- **Keep Episodes**: All, X episodes, X days
- **Quality**: Original, HD, SD
- **Deinterlacing**: Auto
- **Commercial Detection**: Enabled

### Create Recording Rules
Guide > Select Show > Record:
- **Record**: New episodes, All episodes, This episode
- **Keep**: Keep all, Keep X
- **Channel**: Any channel, Specific channel
- **Time Slot**: Any time, Specific time

Or create Pass:
- Advanced rules with keywords
- Time constraints
- Channel filters

### Schedule Manual Recording
Guide > Select show > Record Episode

Or time-based:
Schedule > Add > Manual Recording:
- Channel
- Start time
- Duration

### Watch Recorded Shows
Library > Recorded Shows:
- Play directly in browser
- Stream to devices (iOS, Android, Apple TV, Fire TV)
- Download for offline viewing

### Commercial Detection
Settings > DVR > Commercial Detection:
- **Enabled**: Yes
- **Detection Method**: Comskip
- **Auto-skip**: Optional (requires client support)

Channels automatically detects commercials after recording completes.

## Integration Points

### HDHomeRun
Channels discovers HDHomeRun tuners automatically:
- Network scanning (UDP broadcast)
- Or manual IP entry

### Plex
Export recordings to Plex:
Settings > Sharing > Plex:
- Plex server URL
- Plex token
- Library section

### Homepage Dashboard
```yaml
- Channels DVR:
    icon: channels.png
    href: http://localhost:8089
    description: Live TV and DVR
```

**Note**: Channels DVR uses a custom icon.
- **Icon**: `homepage/config/icons/channels-dvr.png`
- **Label**: `homepage.icon=/icons/channels-dvr.png`

### SWAG reverse proxy
```
Domain: channels.benlawson.dev
Forward: http://channels-dvr:8089
Websockets: Yes
SSL: Let's Encrypt
```

## Troubleshooting

### Tuner Not Detected
1. Verify network connectivity
2. Check HDHomeRun is on same network
3. Use `network_mode: host` for Docker
4. Manually add tuner by IP
5. Check firewall rules

### Recording Failed
1. Check disk space
2. Verify tuner availability
3. Review channel signal strength
4. Check recording logs
5. Ensure TV source is active

### Commercial Detection Not Working
1. Verify Comskip is enabled
2. Check CPU resources available
3. Review detection logs
4. Some channels may not support detection
5. Manual detection: Library > Show > Detect Commercials

### Streaming Buffering
1. Check network bandwidth
2. Reduce streaming quality
3. Enable hardware transcoding (if available)
4. Check CPU usage during transcoding

### Guide Data Missing
1. Verify TV source is configured
2. Check guide provider status
3. Update guide data: Settings > Guide > Update
4. Check subscription/license status

## Best Practices

1. **Storage**: Dedicated high-capacity drive for recordings
2. **Tuners**: Multiple tuners for simultaneous recordings
3. **Commercial Detection**: Enable for automatic ad removal
4. **Backups**: Regular backups of config directory
5. **Quality**: Record at original quality, transcode for mobile
6. **Pass Rules**: Use passes for flexible recording automation
7. **Retention**: Set realistic retention policies per show

## Security Considerations

- **License Key**: Protect license key
- **TVE Credentials**: Stored encrypted in database
- **Network Access**: Restrict to local network or VPN
- **HTTPS**: Use reverse proxy for SSL
- **API Access**: Protect admin endpoints

## Advanced Configuration

### Hardware Transcoding (Intel QuickSync)
Requires Intel GPU with QuickSync:
```yaml
devices:
  - /dev/dri:/dev/dri
```

Settings > Streaming > Hardware Encoding: Intel QuickSync

### Remote Access
Settings > Remote Access:
- **Enable**: Yes
- **Port**: 8089
- **External URL**: https://channels.example.com

Configure port forwarding on router.

### Custom Channel Numbers
Sources > [Source] > Edit Channels:
- Renumber channels
- Hide unwanted channels
- Favorite channels

### Recording Profiles
Different quality profiles:
- **Original**: No transcoding, largest file
- **HD 1080p**: 1080p max, ~5GB/hour
- **HD 720p**: 720p max, ~3GB/hour
- **SD**: ~1GB/hour

### Post-Processing Scripts
Settings > DVR > Post-Processing:
- Custom script after recording
- Example: Auto-convert format, move files, notify

### Virtual Channels
Create custom channels from streaming sources:
- Combine multiple sources
- Custom EPG data
- Scheduled content

## Monitoring

### System Status
Dashboard:
- Active recordings
- Tuner usage
- Disk space
- Guide data status

### Recording History
Library > History:
- All recordings
- Success/failure status
- Duration and file size

### Logs
Settings > Logs:
- DVR engine logs
- Commercial detection logs
- Streaming logs

## API Usage

### Get Recordings
```powershell
Invoke-RestMethod -Uri "http://localhost:8089/dvr/files"
```

### Schedule Recording
```powershell
$body = @{
    channel = "12345"
    time = "2024-01-15T20:00:00Z"
    duration = 3600
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8089/dvr/jobs" -Method Post -Body $body -ContentType "application/json"
```

### Get Guide Data
```powershell
Invoke-RestMethod -Uri "http://localhost:8089/guide/channels"
```

## Backup and Restore

### Backup Config
```powershell
docker compose stop
tar -czf "channels-dvr-config-$(Get-Date -Format 'yyyyMMdd').tar.gz" config/
docker compose start
```

### Restore Config
```powershell
docker compose stop
tar -xzf channels-dvr-config-YYYYMMDD.tar.gz
docker compose start
```

### Backup Recordings
Recordings are standard video files, backup like any media.

## Commercial Detection

### Comskip Configuration
Settings > DVR > Commercial Detection:
- **Sensitivity**: Low, Medium, High
- **Method**: Logo detection, Scene change, Audio

### Manual Commercial Marking
Library > Show > Edit Commercial Breaks:
- Add commercial markers manually
- Adjust auto-detected markers

### Client Support
Not all clients support auto-skip. Markers are embedded in metadata.

## Multiple Tuner Management

### Tuner Priorities
Settings > Sources > [Source] > Priority:
- Set tuner priority order
- Prefer HD over SD sources
- Conflict resolution

### Simultaneous Recordings
- 2 tuners: Record 2 shows simultaneously
- 4 tuners: Record 4 shows simultaneously
- Channels warns about conflicts

## TV Source Types

### HDHomeRun (OTA/Cable)
- Local tuner device
- Best quality (uncompressed)
- Requires antenna or cable card

### TV Everywhere (TVE)
- Streaming from cable provider
- Requires cable subscription
- Internet-based, no tuner needed

### Pluto TV
- Free streaming channels
- Internet-based
- Limited DVR features (some channels)

### Custom M3U
- IPTV sources
- Custom streaming feeds
- Flexible but unsupported

## Recording Quality

### File Sizes (approximate)
- **Original HD**: 3-5GB per hour
- **Transcoded 1080p**: 2-3GB per hour
- **Transcoded 720p**: 1-2GB per hour
- **SD**: 0.5-1GB per hour

### Format
- Container: MPEG-TS (.ts) or MP4
- Codecs: H.264, AAC audio
- Metadata: Series, episode info

## Client Apps

### Official Clients
- **iOS/iPadOS**: Channels app (App Store)
- **Android**: Channels app (Play Store)
- **Apple TV**: Native tvOS app
- **Fire TV**: Amazon Appstore
- **Web**: Browser-based player

### Features
- Live TV streaming
- DVR playback
- Commercial skip
- Remote access
- Downloads (mobile)

This comprehensive DVR solution provides professional TV recording and management with commercial detection, multi-device streaming, and extensive customization for the homelab media stack.
