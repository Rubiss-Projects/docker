# Speedtest Tracker Guidance

Use this guidance when working on Speedtest Tracker configuration and network performance monitoring.

## Service Overview
Speedtest Tracker is a self-hosted internet speed test application that runs automated speed tests using Ookla Speedtest and stores historical results. It provides visualization of internet performance trends over time with charts and notifications for degraded performance.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "8080:80"  # Or custom port
  - "8443:443"  # HTTPS
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/Chicago
  - APP_KEY=base64:...  # Generate with artisan
  - DB_CONNECTION=sqlite  # Or mysql/pgsql
volumes:
  - ./data:/config
restart: unless-stopped
```

### Critical Files
- `data/database.sqlite` - SQLite database (default)
- `data/.env` - Application configuration
- `data/log/` - Application logs

### Default Ports
- 80/443 - Web UI (mapped to 8080/8443 typically)

## Common Tasks

### First-Time Setup
1. Generate APP_KEY:
   ```powershell
   docker exec speedtest-tracker php artisan key:generate --show
   ```
2. Add to docker-compose.yml:
   ```yaml
   - APP_KEY=base64:generated_key_here
   ```
3. Restart container
4. Access: `http://localhost:8080`
5. Complete setup wizard (create admin account)

### Manual Speed Test
Dashboard > Run Test:
- Immediate speed test execution
- Results appear in ~30-60 seconds
- Shows: Download, Upload, Ping, Jitter
- Server location and ISP info

### Schedule Automatic Tests
Settings > Schedule:
1. **Frequency**: Hourly, Every 3 hours, Every 6 hours, Daily
2. **Time**: Specific time of day (for daily)
3. **Random Offset**: Add 0-15 min random delay to avoid detection
4. **Save**

Example cron expressions:
- `0 * * * *` - Every hour
- `0 */6 * * *` - Every 6 hours
- `0 2 * * *` - Daily at 2 AM

### View Results History
Dashboard:
- **Latest Results**: Most recent test
- **Chart**: Download/upload/ping over time
- **Table**: All historical tests
- **Filters**: Date range, result type
- **Export**: CSV/JSON export

### Configure Speedtest Settings
Settings > Speedtest:
1. **Server**: Auto, or select specific server ID
2. **Timeout**: Test timeout in seconds
3. **Test Frequency**: Schedule configuration
4. **Results Retention**: Keep results for X days

### Set Performance Thresholds
Settings > Thresholds:
- **Minimum Download**: 50 Mbps (alert if below)
- **Minimum Upload**: 10 Mbps
- **Maximum Ping**: 50 ms
- **Maximum Jitter**: 10 ms

Alerts trigger when thresholds not met.

## Integration Points

### Homepage Dashboard
```yaml
- Speedtest Tracker:
    icon: speedtest-tracker.png
    href: http://localhost:8080
    description: Internet speed monitoring
    widget:
      type: speedtest-tracker
      url: http://speedtest-tracker:80
```

Widget shows:
- Latest download speed
- Latest upload speed
- Latest ping

### SWAG reverse proxy
```
Domain: speedtest.benlawson.dev
Forward: http://speedtest-tracker:80
SSL: Let's Encrypt
```

### Notifications (Webhooks)
Settings > Notifications:
- **Discord Webhook**: Speed test results to Discord
- **Custom Webhook**: POST JSON to any URL
- **Slack**: Results to Slack channel

Example Discord webhook payload:
```json
{
  "content": "Speed test complete",
  "embeds": [{
    "title": "Results",
    "fields": [
      {"name": "Download", "value": "100 Mbps"},
      {"name": "Upload", "value": "20 Mbps"},
      {"name": "Ping", "value": "15 ms"}
    ]
  }]
}
```

### Prometheus Exporter (Community)
No official exporter, but results can be scraped via API.

## Troubleshooting

### APP_KEY Error
```
Error: No application encryption key has been specified
```

**Fix**:
```powershell
docker exec speedtest-tracker php artisan key:generate --show
# Copy output and add to docker-compose.yml
# APP_KEY=base64:...
docker compose up -d
```

### Speed Test Fails
1. Check Ookla Speedtest CLI is working:
   ```powershell
   docker exec speedtest-tracker speedtest
   ```
2. Network connectivity from container
3. Firewall blocking outbound connections
4. Review logs: `data/log/laravel.log`

### Database Locked
SQLite database locked:
1. Stop container
2. Check no other processes accessing DB
3. Restart container
4. Consider switching to MySQL/PostgreSQL for multi-user

### Scheduled Tests Not Running
1. Check cron is configured: Settings > Schedule
2. Review logs for errors
3. Verify container timezone: `TZ=America/Chicago`
4. Check Laravel scheduler is running:
   ```powershell
   docker exec speedtest-tracker php artisan schedule:list
   ```

### Slow Web UI
1. Clear Laravel cache:
   ```powershell
   docker exec speedtest-tracker php artisan cache:clear
   docker exec speedtest-tracker php artisan config:clear
   docker exec speedtest-tracker php artisan view:clear
   ```
2. Optimize:
   ```powershell
   docker exec speedtest-tracker php artisan optimize
   ```

## Best Practices

1. **Test Frequency**: Every 3-6 hours balances data vs. bandwidth usage
2. **Random Offset**: Avoid ISP throttling detection
3. **Retention**: Keep 90-180 days of history
4. **Backups**: Backup database regularly
5. **Server Selection**: Use consistent server for comparable results
6. **Thresholds**: Set realistic alerts based on your ISP plan
7. **HTTPS**: Use reverse proxy for SSL

## Security Considerations

- **Authentication**: Strong admin password
- **HTTPS**: Use reverse proxy for SSL
- **APP_KEY**: Keep secret, rotate periodically
- **Database**: Restrict access to SQLite file
- **Network**: Results contain ISP and location info
- **API Access**: Protect API endpoints

## Advanced Configuration

### Database: MySQL/PostgreSQL
For better performance with many users:

```yaml
environment:
  - DB_CONNECTION=mysql
  - DB_HOST=mysql
  - DB_PORT=3306
  - DB_DATABASE=speedtest_tracker
  - DB_USERNAME=speedtest
  - DB_PASSWORD=secure_password
```

Create database first:
```sql
CREATE DATABASE speedtest_tracker;
CREATE USER 'speedtest'@'%' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON speedtest_tracker.* TO 'speedtest'@'%';
```

### Custom Speedtest Server
To use specific server (for consistency):
1. Find server ID:
   ```powershell
   docker exec speedtest-tracker speedtest --servers
   ```
2. Settings > Speedtest > Server ID: 12345

### Multiple Users
Create additional users (admin only):
1. Settings > Users > Add User
2. Username, email, password
3. Role: Admin or User
4. Users can view results, only admins can run tests

### API Access
Get API token:
1. Settings > API > Generate Token
2. Use in requests:
   ```powershell
   $headers = @{ "Authorization" = "Bearer your-token" }
   Invoke-RestMethod -Uri "http://localhost:8080/api/results" -Headers $headers
   ```

### Custom Thresholds Per Time
Different thresholds for different times:
- Peak hours: Lower expectations
- Off-peak: Full speed expected

(Requires custom scripting via API)

## Charts and Visualizations

### Available Charts
- **Download Speed Over Time**: Line chart
- **Upload Speed Over Time**: Line chart
- **Ping Over Time**: Line chart
- **Combined Chart**: All metrics
- **Statistical Summary**: Min/Max/Average

### Export Data
Dashboard > Export:
- **CSV**: Spreadsheet import
- **JSON**: API consumption
- Date range filter
- All metrics included

### Grafana Integration (DIY)
Export results to InfluxDB or Prometheus:
1. Use API to fetch results
2. Push to time-series database
3. Create Grafana dashboards

Example: Custom script to export to InfluxDB every hour.

## Monitoring and Alerts

### Performance Degradation Detection
Automatic alerts when:
- Download speed < threshold
- Upload speed < threshold
- Ping > threshold
- Packet loss detected

### Notification Channels
Configure webhooks for:
- **Discord**: Speed test results
- **Slack**: Performance alerts
- **Email**: Critical degradation (requires SMTP config)
- **Custom Webhook**: Integrate with any system

### Alert Frequency
Settings > Notifications:
- **Immediate**: Alert on every failed test
- **Throttled**: Max 1 alert per hour
- **Daily Digest**: Summary email

## Common Use Cases

### ISP Accountability
Track actual speeds vs. advertised:
- Document consistent underperformance
- Evidence for ISP support tickets
- Identify peak congestion times

### Network Troubleshooting
Correlate speed degradation with:
- Specific times of day
- Weather events
- Equipment changes
- ISP outages

### Home Lab Performance
Monitor impact of:
- Heavy downloads on network
- Streaming quality issues
- Game lag correlation
- VPN overhead

## Backup and Restore

### Backup SQLite
```powershell
docker compose stop
Copy-Item data/database.sqlite "speedtest-backup-$(Get-Date -Format 'yyyyMMdd').sqlite"
docker compose start
```

### Backup with MySQL
```powershell
docker exec mysql mysqldump -u speedtest -p speedtest_tracker > backup.sql
```

### Restore SQLite
```powershell
docker compose stop
Copy-Item backup.sqlite data/database.sqlite
docker compose start
```

## Performance Optimization

### Database Optimization
```powershell
# SQLite vacuum
docker exec speedtest-tracker php artisan db:vacuum

# Clear old results (older than 180 days)
docker exec speedtest-tracker php artisan results:prune --days=180
```

### Laravel Optimization
```powershell
docker exec speedtest-tracker php artisan config:cache
docker exec speedtest-tracker php artisan route:cache
docker exec speedtest-tracker php artisan view:cache
```

## Environment Variables

### Essential
- `APP_KEY` - Encryption key (required)
- `TZ` - Timezone (e.g., America/Chicago)
- `PUID/PGID` - User/group permissions

### Database
- `DB_CONNECTION` - sqlite, mysql, pgsql
- `DB_HOST` - Database host
- `DB_PORT` - Database port
- `DB_DATABASE` - Database name
- `DB_USERNAME` - Database user
- `DB_PASSWORD` - Database password

### Application
- `APP_URL` - Base URL (e.g., https://speedtest.example.com)
- `APP_DEBUG` - Debug mode (false in production)
- `APP_ENV` - Environment (production, local)

### Mail (SMTP)
- `MAIL_MAILER` - smtp
- `MAIL_HOST` - smtp.gmail.com
- `MAIL_PORT` - 587
- `MAIL_USERNAME` - email@gmail.com
- `MAIL_PASSWORD` - app-password
- `MAIL_ENCRYPTION` - tls
- `MAIL_FROM_ADDRESS` - noreply@example.com

## Artisan Commands

### Key Management
```powershell
docker exec speedtest-tracker php artisan key:generate
```

### Database
```powershell
docker exec speedtest-tracker php artisan migrate
docker exec speedtest-tracker php artisan db:seed
```

### Cache
```powershell
docker exec speedtest-tracker php artisan cache:clear
docker exec speedtest-tracker php artisan config:clear
docker exec speedtest-tracker php artisan route:clear
docker exec speedtest-tracker php artisan view:clear
```

### Maintenance
```powershell
# Enter maintenance mode
docker exec speedtest-tracker php artisan down

# Exit maintenance mode
docker exec speedtest-tracker php artisan up

# Prune old results
docker exec speedtest-tracker php artisan results:prune --days=90
```

This automated speed testing solution provides historical internet performance tracking with visualizations and alerts for the homelab network monitoring stack.
