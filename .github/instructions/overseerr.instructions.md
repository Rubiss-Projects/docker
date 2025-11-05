---
applyTo: "overseerr/**"
---

# Overseerr Expert Instructions

You are an expert in Overseerr media request and discovery management.

## Service Overview
Overseerr is a request management and media discovery tool for Plex. It allows users to request movies and TV shows, which are automatically sent to Radarr/Sonarr for download. Features include user management, notifications, and integration with Plex watchlists.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "5055:5055"
volumes:
  - ./config:/app/config
environment:
  - LOG_LEVEL=info
  - TZ=America/New_York
networks:
  - proxynet
restart: unless-stopped
```

### Critical Files
- `config/settings.json` - All Overseerr configuration
- `config/db/db.sqlite3` - User data, requests, notifications

### Default Port
- 5055 - Web UI

## Common Tasks

### First-Time Setup
1. Access: `http://localhost:5055`
2. Sign in with Plex account
3. Configure Plex server:
   - URL: `http://plex:32400`
   - Use SSL: Unchecked (internal)
   - Test connection
4. Sync Plex libraries
5. Configure Radarr:
   - URL: `http://radarr:7878`
   - API Key: From Radarr settings
   - Root folder, quality profile
6. Configure Sonarr:
   - URL: `http://sonarr:8989`
   - API Key: From Sonarr settings
   - Root folder, quality profile
7. Set up users and permissions

### Request Movie/TV Show
**As User:**
1. Search for title
2. Click title > Request
3. Select quality (if options available)
4. Add optional note
5. Submit request

**Auto-Approval:**
- Admin/users with permissions get instant approval
- Requests automatically sent to Radarr/Sonarr

### Manage Requests
**Admin Panel:**
1. Requests page
2. View pending/approved/declined
3. Approve/decline with notes
4. Track download status from *arr services

### User Management
Settings > Users:
- Import from Plex
- Set request limits (per day/week/month)
- Grant admin/auto-approve permissions
- Manage quotas

### Notifications
Settings > Notifications:
- Discord webhook
- Email (SMTP)
- Slack
- Telegram
- Pushover
- Webhooks (custom)

Configure triggers:
- Media requested
- Media approved/declined
- Media available (downloaded)
- Media failed

## Integration Points

### Plex Integration
- Uses Plex for authentication
- Syncs libraries to show availability
- Imports Plex users automatically
- Watchlist integration (auto-request from Plex watchlist)

### Radarr Integration
```
URL: http://radarr:7878
API Key: [From Radarr Settings > General]
Default Root Folder: /movies
Default Quality Profile: HD-1080p
Default Minimum Availability: Released
```

### Sonarr Integration
```
URL: http://sonarr:8989
API Key: [From Sonarr Settings > General]
Default Root Folder: /tv
Default Quality Profile: HD-1080p
Default Language Profile: English
Season Folder: Enabled
```

### Homepage Dashboard
```yaml
- Overseerr:
    icon: overseerr.png
    href: https://overseerr.benlawson.dev
    description: Media requests
    widget:
      type: overseerr
      url: http://overseerr:5055
      key: ${OVERSEERR_API_KEY}
```

Get API key: Settings > General > API Key

### Nginx Proxy Manager
```
Domain: overseerr.benlawson.dev
Forward: http://overseerr:5055
Websockets: No
SSL: Let's Encrypt
```

## Troubleshooting

### Cannot Sign In with Plex
1. Verify Plex server is accessible
2. Check Plex token is valid
3. Clear browser cache
4. Try different browser

### Radarr/Sonarr Connection Failed
1. Verify *arr service is running
2. Test URLs: `http://radarr:7878` from Overseerr container
3. Check API keys are correct
4. Ensure all services on proxynet network

### Requests Not Appearing in Radarr/Sonarr
1. Check request was approved
2. Verify *arr integration is enabled
3. Review Overseerr logs
4. Check *arr activity queue

### Email Notifications Not Sending
1. Configure SMTP settings
2. Test SMTP connection
3. Check spam folder
4. Verify email template is enabled

## Best Practices

1. **User Quotas**: Set reasonable request limits
2. **Auto-Approval**: Grant to trusted users only
3. **Quality Profiles**: Match *arr service profiles
4. **Regular Backups**: Backup config directory
5. **Notifications**: Enable for admins at minimum
6. **Plex Sync**: Run periodically to update availability
7. **Request Limits**: Prevent abuse with quotas
8. **User Permissions**: Use role-based access

## Security Considerations

- **Plex Authentication**: OAuth via Plex account
- **Local Users**: Can be created without Plex
- **Password Protection**: Enforce strong passwords
- **API Key**: Keep secret, regenerate if compromised
- **External Access**: Use HTTPS via NPM
- **Request Approval**: Require for untrusted users

## Advanced Configuration

### User Permissions
Settings > Users > Edit User:
- **Admin**: Full access to settings
- **Manage Requests**: Approve/decline any request
- **Manage Users**: Create/edit user accounts
- **Request 4K**: Allow 4K content requests
- **Auto-Approve Movies**: Skip approval process
- **Auto-Approve Series**: Skip approval for TV

### Request Quotas
Per user or role:
- Movies per day/week/month
- TV episodes per day/week/month
- Unlimited for admins

### Watchlist Sync
Settings > Plex > Enable Plex Watchlist:
- Automatically request items added to Plex watchlist
- Sync interval: 1-24 hours
- Applies to all users or specific users

### Custom Notifications
Settings > Notifications > Webhook:
```json
{
  "event": "{{event}}",
  "subject": "{{subject}}",
  "message": "{{message}}",
  "media": {
    "title": "{{media_title}}",
    "type": "{{media_type}}",
    "tmdb_id": "{{media_tmdbid}}"
  },
  "request": {
    "username": "{{request_username}}",
    "status": "{{request_status}}"
  }
}
```

### Multiple *arr Instances
Add multiple Radarr/Sonarr servers:
- Default server (Standard)
- 4K server (Ultra HD)
- Separate servers for different quality tiers

### Public Sign-Up
Settings > General:
- Enable new Plex sign-ins: Allow anyone with Plex
- Default permissions: Set for new users
- Welcome message: Display on login

## Monitoring

### Request Statistics
Dashboard shows:
- Total requests
- Pending approval count
- Available media count
- Processing/errored requests

### Activity Feed
Recent activity:
- New requests
- Approvals/denials
- Media availability
- User activity

## Common Errors

### "Failed to connect to Plex"
- Plex server offline
- Incorrect Plex URL
- Network connectivity issue

### "Radarr/Sonarr API returned an error"
- Invalid API key
- Service not running
- Incompatible version

### "Media already exists"
- Already in Plex library
- Pending request for same title
- Check library sync status

## API Usage

### Get Requests
```powershell
$headers = @{ "X-Api-Key" = $env:OVERSEERR_API_KEY }
Invoke-RestMethod -Uri "http://localhost:5055/api/v1/request" -Headers $headers
```

### Search Media
```powershell
Invoke-RestMethod -Uri "http://localhost:5055/api/v1/search?query=Inception" -Headers $headers
```

### Create Request
```powershell
$body = @{
    mediaType = "movie"
    mediaId = 27205  # TMDB ID
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5055/api/v1/request" -Method Post -Headers $headers -Body $body -ContentType "application/json"
```

## Backup and Restore

### Backup
```powershell
docker compose stop
tar -czf overseerr-backup-$(Get-Date -Format "yyyyMMdd").tar.gz config/
docker compose start
```

### Restore
```powershell
docker compose stop
tar -xzf overseerr-backup-YYYYMMDD.tar.gz
docker compose start
```

## Performance Tips

- Enable library sync caching
- Limit concurrent API requests
- Use local images cache
- Reduce Plex sync frequency if large library

This request management system streamlines media acquisition for Plex users with approval workflows and automated *arr integration.
