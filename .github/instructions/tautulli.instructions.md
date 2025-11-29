---
applyTo: "tautulli/**"
---

# Tautulli Expert Instructions

You are an expert in Tautulli for Plex monitoring and statistics.

## Service Overview
Tautulli (formerly PlexPy) monitors and tracks Plex Media Server usage. It provides detailed statistics, history, notifications, and insights into who's watching what, when, and how.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "8181:8181"
volumes:
  - ./config:/config
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/New_York
networks:
  - proxynet
restart: unless-stopped
```

### Critical Files
- `config/config.ini` - Tautulli configuration
- `config/tautulli.db` - Statistics database
- `config/logs/` - Application logs

### Default Port
- 8181 - Web UI

## Common Tasks

### First-Time Setup
1. Access: `http://localhost:8181`
2. Setup wizard:
   - Plex Server URL: `http://plex:32400`
   - Plex Token: Get from Plex Web (Account > Settings)
3. Verify connection
4. Wait for initial data sync

### Get Plex Token
1. Open Plex Web
2. Play any media
3. Click Info (i) button
4. View XML
5. Find `X-Plex-Token=XXXXX` in URL

### View Watch History
Home > History:
- All plays with start/stop times
- User, media title, platform
- Duration watched, completion %
- Play method (direct play/transcode)

### View Statistics
Graphs and stats for:
- Plays by day/month/year
- Most watched content
- User activity
- Peak streaming hours
- Bandwidth usage

### View Current Activity
Home > Current Activity:
- Active streams in real-time
- User, media, player
- Transcoding status
- Bandwidth per stream

### Recently Added
Home > Recently Added:
- New media in Plex libraries
- Filterable by library
- Links to media details

## Integration Points

### Plex Connection
Settings > Plex Media Server:
- URL: `http://plex:32400`
- Plex Token: From Plex Web
- Verify SSL: Unchecked (internal)
- Test connection

### Notifications
Settings > Notification Agents:
- Discord
- Email
- Slack
- Telegram
- Pushover
- Twitter
- Webhooks

Notification triggers:
- Playback start/stop/pause/resume
- Watched (85% completion)
- New media added to Plex
- Server down/back up
- Transcode decision change
- User concurrent streams

### Homepage Dashboard
```yaml
- Tautulli:
    icon: tautulli.png
    href: http://localhost:8181
    description: Plex statistics
    widget:
      type: tautulli
      url: http://tautulli:8181
      key: ${TAUTULLI_API_KEY}
```

Get API key: Settings > Web Interface > API

### Scripts
Settings > Notification Agents > Script:
- Run custom scripts on events
- Parameters: {username}, {title}, {action}, etc.
- Use for custom automation

## Troubleshooting

### Cannot Connect to Plex
1. Verify Plex is running: `docker ps`
2. Test URL: `curl http://plex:32400`
3. Check Plex token is valid
4. Ensure both on proxynet network

### No Activity Shown
1. Check Plex is actively streaming
2. Verify connection to Plex
3. Restart Tautulli: `docker compose restart`
4. Review logs: Settings > Logs

### Statistics Not Updating
1. Check Plex database sync: Settings > Plex Media Server
2. Force library refresh
3. Verify Plex token hasn't changed
4. Check database integrity

### Notifications Not Sending
1. Test notification agent
2. Verify trigger conditions
3. Check notification template
4. Review Tautulli logs

## Best Practices

1. **Regular Backups**: Backup config and database
2. **Monitor Usage**: Track server performance
3. **User Privacy**: Respect user viewing data
4. **Notifications**: Alert on server issues
5. **Database Maintenance**: Vacuum database periodically
6. **Update Regularly**: Keep Tautulli current

## Security Considerations

- **Authentication**: Enable password protection
- **API Key**: Keep secret, regenerate if exposed
- **External Access**: Use HTTPS via SWAG
- **User Data**: Viewing history is sensitive
- **Admin Access**: Limit to trusted users

## Advanced Configuration

### Custom Notifications
Create notification rules with conditions:
- User is/is not specific user
- Library is/is not specific library
- Media type is movie/episode/track
- Transcode decision is transcode/direct play
- Stream count is above/below threshold

Example: Alert when >3 concurrent transcodes

### Newsletters
Settings > Newsletters:
- Automatically email recently added content
- Schedule: Daily/weekly/monthly
- Include posters, summaries
- Per-user customization

### Scripts on Events
```powershell
# kill-stream.ps1
param($sessionKey)
# Kill problematic stream
tautulli_api.ps1 -cmd terminate_session -session_key $sessionKey
```

Trigger on: Concurrent streams > limit

### Plex Web Integration
Settings > Web Interface > Plex Web:
- Add Tautulli link to Plex Web
- Quick access from Plex interface

### Database Backup Schedule
Settings > Backup/Restore:
- Automatic database backups
- Retention: 7 days
- Location: `config/backups/`

### User Watching Habits
Home > User > [Username]:
- Most watched genres
- Preferred watch times
- Device usage
- Library access stats

## Monitoring

### Server Performance
Home > Graphs:
- Bandwidth usage over time
- Concurrent streams
- Transcode count
- Library growth

### User Activity
Home > Users:
- Total plays per user
- Watch time
- Last seen
- Device breakdown

### Library Statistics
Home > Libraries:
- Play count per library
- Most played items
- Recently added count
- Library size/duration

## Common Errors

### "Unable to connect to Plex"
- Plex server offline
- Wrong URL or token
- Network issue

### "Database locked"
- Concurrent write operations
- Restart Tautulli
- Check disk I/O

### Missing plays in history
- Plex didn't record play (too short)
- Database sync issue
- Check Plex logs

## API Usage

### Get Activity
```powershell
$headers = @{ "apikey" = $env:TAUTULLI_API_KEY }
Invoke-RestMethod -Uri "http://localhost:8181/api/v2?cmd=get_activity" -Headers $headers
```

### Get History
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/api/v2?cmd=get_history&length=25" -Headers $headers
```

### Get User Stats
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/api/v2?cmd=get_user&user_id=1" -Headers $headers
```

### Terminate Stream
```powershell
$body = @{
    cmd = "terminate_session"
    session_key = "abc123"
    message = "Your stream has been stopped"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8181/api/v2" -Method Post -Headers $headers -Body $body
```

## Useful Queries

### Most Active Users
Home > Users > Sort by Plays

### Bandwidth Hogs
Home > History > Sort by Bandwidth

### Transcoding Stats
Home > Graphs > Stream Type by Stream

### Popular Content
Home > Libraries > [Library] > Popular

## Backup and Restore

### Backup
```powershell
docker compose stop
tar -czf tautulli-backup-$(Get-Date -Format "yyyyMMdd").tar.gz config/
docker compose start
```

### Database Only
```powershell
cp config/tautulli.db config/tautulli-backup.db
```

### Restore
```powershell
docker compose stop
tar -xzf tautulli-backup-YYYYMMDD.tar.gz
docker compose start
```

## Performance Tips

- Increase database cache size in config.ini
- Limit history retention (Settings > General)
- Vacuum database monthly
- Monitor log file size

This monitoring tool provides invaluable insights into Plex usage patterns, server performance, and user behavior for optimization and troubleshooting.
