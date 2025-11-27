---
applyTo: "uptime-kuma/**"
---

# Uptime Kuma Expert Instructions

You are an expert in Uptime Kuma monitoring and alerting configuration.

## Service Overview
Uptime Kuma is a self-hosted uptime monitoring tool similar to Upstatuspage. It provides real-time monitoring for websites, TCP ports, HTTP(S), DNS, Docker containers, and more with a beautiful web UI and multi-channel notifications.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "3001:3001"
volumes:
  - ./data:/app/data
  - /var/run/docker.sock:/var/run/docker.sock  # Optional: for Docker monitoring
restart: unless-stopped
```

### Critical Files
- `data/kuma.db` - SQLite database with all monitors
- `data/upload/` - Custom icons/logos

### Default Port
- 3001 - Web UI

## Common Tasks

### First-Time Setup
1. Access: `http://localhost:3001`
2. Create admin account
3. Set display name
4. Dashboard appears

### Add HTTP(S) Monitor
Monitors > Add New Monitor:
1. **Monitor Type**: HTTP(s)
2. **Friendly Name**: My Website
3. **URL**: https://example.com
4. **Heartbeat Interval**: 60 seconds
5. **Retries**: 0
6. **Accepted Status Codes**: 200-299
7. **Save**

### Add TCP Port Monitor
1. **Monitor Type**: TCP Port
2. **Hostname**: 192.168.1.100
3. **Port**: 22
4. **Heartbeat Interval**: 60 seconds
5. **Save**

### Add Ping Monitor
1. **Monitor Type**: Ping
2. **Hostname**: 8.8.8.8
3. **Heartbeat Interval**: 60 seconds
4. **Save**

### Add Docker Container Monitor
(Requires Docker socket mount)
1. **Monitor Type**: Docker Container
2. **Docker Container**: container_name
3. **Docker Host**: unix:///var/run/docker.sock
4. **Heartbeat Interval**: 60 seconds
5. **Save**

### Configure Notifications
Settings > Notifications > Setup Notification:

**Discord**:
- Notification Type: Discord
- Webhook URL: (from Discord server settings)
- Friendly Name: Discord Alerts
- Test notification

**Email (SMTP)**:
- Notification Type: Email (SMTP)
- SMTP Host: smtp.gmail.com
- Port: 587
- Security: TLS
- Username: your-email@gmail.com
- Password: app-password
- From: your-email@gmail.com
- To: alerts@example.com

**Pushover**:
- User Key: (from Pushover)
- App Token: (from Pushover)

**Telegram**:
- Bot Token: (from BotFather)
- Chat ID: (your chat ID)

**Slack**:
- Webhook URL: (from Slack)

### Assign Notifications to Monitors
Monitor > Edit > Notifications:
- Check notifications to enable
- Default is "apply on all existing monitors"
- Per-monitor overrides available

## Integration Points

### Homepage Dashboard
```yaml
- Uptime Kuma:
    icon: uptime-kuma.png
    href: http://localhost:3001
    description: Service monitoring
    widget:
      type: uptimekuma
      url: http://uptime-kuma:3001
      slug: default  # Status page slug
```

### Nginx Proxy Manager
```
Domain: uptime.benlawson.dev
Forward: http://uptime-kuma:3001
Websockets: Yes (required)
SSL: Let's Encrypt
```

### Prometheus (Unofficial Exporter)
Uptime Kuma doesn't have native Prometheus export, but community exporters exist.

### Public Status Page
Settings > Status Pages > Add New:
1. Title: My Services
2. Slug: status
3. Description: Service status dashboard
4. Add monitors to display
5. Custom domain: status.example.com
6. Public URL: `http://localhost:3001/status/status`

## Troubleshooting

### Cannot Access UI
1. Check container: `docker ps`
2. Test port: `curl http://localhost:3001`
3. Check logs: `docker logs uptime-kuma`
4. Verify port not in use

### Monitor Shows "Down" (False Positive)
1. Check network connectivity from container
2. Verify URL/hostname is correct
3. Increase timeout setting
4. Check accepted status codes
5. Review monitor logs

### Notifications Not Sending
1. Test notification in settings
2. Check webhook URL is correct
3. Verify SMTP settings for email
4. Check notification is assigned to monitor
5. Review Uptime Kuma logs

### Docker Container Monitoring Not Working
1. Verify Docker socket is mounted:
   ```yaml
   volumes:
     - /var/run/docker.sock:/var/run/docker.sock
   ```
2. Check container name is correct
3. Verify permissions on socket

### Database Locked Errors
1. Stop container
2. Remove WAL lock files:
   ```bash
   rm -f /mnt/e/Docker/uptime-kuma/data/kuma.db-shm /mnt/e/Docker/uptime-kuma/data/kuma.db-wal
   ```
3. Restart container

### Database Growing Large / Slow Performance
The SQLite database (`kuma.db`) can grow very large over time due to heartbeat data accumulation. A 600MB+ database will cause slow UI loading.

**Fix:**
1. Set retention in UI: **Settings → General → Keep History** (e.g., 30 days)
2. Stop container:
   ```bash
   docker stop uptime-kuma
   ```
3. Delete old heartbeat data and vacuum:
   ```bash
   docker run --rm -v /mnt/e/Docker/uptime-kuma/data:/data alpine/sqlite /data/kuma.db "DELETE FROM heartbeat WHERE time < datetime('now', '-30 days');"
   docker run --rm -v /mnt/e/Docker/uptime-kuma/data:/data alpine/sqlite /data/kuma.db "VACUUM;"
   ```
4. Start container:
   ```bash
   docker start uptime-kuma
   ```

**Note:** The UI "Shrink Database" button may not work well with large databases. Use the manual method above for best results.

## Best Practices

1. **Heartbeat Intervals**: Balance monitoring frequency vs. resource usage
2. **Retries**: Set retries to avoid false alerts during brief outages
3. **Maintenance Windows**: Schedule maintenance to pause alerts
4. **Tags**: Organize monitors with tags (Production, Staging, etc.)
5. **Status Pages**: Create public status pages for customer communication
6. **Backup Database**: Regular backups of kuma.db
7. **Notification Groups**: Group related monitors for targeted alerts

## Security Considerations

- **Authentication**: Strong admin password
- **HTTPS**: Use reverse proxy with SSL
- **Public Status Pages**: Consider what to expose publicly
- **API Keys**: Protect status page API keys
- **Docker Socket**: Full Docker access if mounted
- **Network Access**: Monitor can test internal services
- **Password Storage**: Encrypted in database

## Advanced Configuration

### Monitor Groups
Organize monitors:
1. Add Tag to monitors (e.g., "Production")
2. Filter dashboard by tag
3. Status pages can filter by tag

### Maintenance Windows
Monitor > Edit > Maintenance:
- Schedule: One-time, recurring
- Date/time range
- Monitors automatically paused during maintenance
- No alerts sent

### Certificate Expiry Monitoring
HTTP(S) monitors automatically check SSL:
- Certificate expiry date
- Days until expiry
- Notification when expiring soon

### DNS Monitoring
Monitor Type: DNS:
- Resolve hostname: example.com
- Record Type: A, AAAA, CNAME, MX, TXT
- Expected Result: 1.2.3.4
- Alerts if DNS changes

### Keyword Monitoring
HTTP(S) monitors can check page content:
- Expected Keyword: "Operational"
- Alert if keyword missing/present

### Custom Headers
HTTP(S) monitors support custom headers:
```
Authorization: Bearer token123
User-Agent: Custom-Monitor
```

### JSON Query Monitoring
HTTP(S) monitors can parse JSON:
- Expected Value: `$.status`
- Expected Result: "ok"
- JSON path query

## Monitoring Types

### HTTP(s)
- GET/POST/PUT/DELETE methods
- Status code checking
- Response time tracking
- SSL certificate monitoring
- Keyword detection

### TCP Port
- Port connectivity check
- Response time

### Ping (ICMP)
- Host reachability
- Packet loss %
- Response time

### DNS
- Record resolution
- Expected IP check
- Response time

### Docker Container
- Container running status
- Restart detection

### Steam Game Server
- Server online status
- Player count

### Gamedig
- Game server monitoring
- Supports many game types

### MongoDB
- Database connection test

### PostgreSQL / MySQL / MariaDB
- Database connection test
- Query execution

### Redis
- Connection test
- PING command

### Tailscale Ping
- Tailscale network monitoring

## API Usage

### Get Monitor List
```powershell
$headers = @{
    "Authorization" = "Bearer your-api-key"
}

Invoke-RestMethod -Uri "http://localhost:3001/api/monitors" -Headers $headers
```

### Push Monitor (Push-based Monitoring)
Create Push monitor in UI, get push URL:
```powershell
# Send heartbeat
Invoke-RestMethod -Uri "http://localhost:3001/api/push/push-key?status=up&msg=OK&ping=123"
```

Parameters:
- status: up/down
- msg: Status message
- ping: Response time in ms

### API Key
Settings > Security > API Keys > Add API Key

## Notifications Channels Supported

- **Email (SMTP)**: Gmail, SendGrid, custom SMTP
- **Webhook**: Generic HTTP POST
- **Discord**: Server webhooks
- **Slack**: Workspace webhooks
- **Telegram**: Bot API
- **Pushover**: Push notifications
- **Pushbullet**: Cross-device notifications
- **Gotify**: Self-hosted notifications
- **Signal**: Secure messaging
- **SMS**: Various providers (Twilio, etc.)
- **Microsoft Teams**: Channel webhooks
- **Google Chat**: Space webhooks
- **Rocket.chat**: Self-hosted chat
- **Matrix**: Decentralized messaging
- **Apprise**: Universal notification library (supports 70+ services)

## Backup and Restore

### Backup
```powershell
docker compose stop
tar -czf uptime-kuma-backup-$(Get-Date -Format "yyyyMMdd").tar.gz data/
docker compose start
```

### Restore
```powershell
docker compose stop
tar -xzf uptime-kuma-backup-YYYYMMDD.tar.gz
docker compose start
```

## Status Page Configuration

### Create Public Status Page
Settings > Status Pages > Add New:
1. **Title**: Service Status
2. **Slug**: status (URL: /status/status)
3. **Description**: Real-time service status
4. **Theme**: Light/Dark
5. **Show Tags**: Yes
6. **Custom Domain**: status.example.com (optional)
7. **Google Analytics**: UA-XXXXX (optional)

### Add Monitors to Status Page
- Select monitors to display
- Group by tags
- Custom descriptions

### Incident Management
- Post incidents manually
- Link to affected monitors
- Update incident status
- Historical incident log

## Performance Optimization

### Database Maintenance
- Uptime Kuma auto-vacuums SQLite
- Keep old data: Settings > Keep History Days
- Default: 180 days

### Reduce Heartbeat Frequency
- For many monitors, use 120-300 second intervals
- Only critical services need 30-60 seconds

### Tag Organization
- Group monitors by category
- Filter dashboard view
- Reduces visual clutter

## Common Monitor Configurations

### Website Uptime
```
Type: HTTP(s)
URL: https://example.com
Interval: 60s
Status Codes: 200-299
Keyword: (optional homepage text)
```

### API Endpoint
```
Type: HTTP(s)
URL: https://api.example.com/health
Method: GET
Interval: 60s
Status Codes: 200
Expected JSON: $.status = "ok"
```

### SSH Service
```
Type: TCP Port
Host: server.example.com
Port: 22
Interval: 60s
```

### Database
```
Type: PostgreSQL
Host: db.example.com
Port: 5432
Database: mydb
Username: monitor
Password: ***
Interval: 300s
```

### SSL Certificate Expiry
```
Type: HTTP(s)
URL: https://example.com
Interval: 86400s (daily)
Monitor SSL expiry
Alert: 30 days before expiry
```

This self-hosted monitoring solution provides comprehensive uptime tracking with beautiful visualizations and flexible alerting for the entire homelab infrastructure.
