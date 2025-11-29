---
applyTo: "grafana/**"
---

# Grafana Expert Instructions

You are an expert in Grafana visualization and dashboard creation for Prometheus data.

## Service Overview
Grafana provides visualization dashboards for metrics collected by Prometheus. It's the primary interface for monitoring container and system health across Windows and Raspberry Pi hosts.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "3000:3000"
volumes:
  - ./data:/var/lib/grafana
environment:
  - GF_SECURITY_ADMIN_USER=admin
  - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
  - GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource
  - GF_SERVER_ROOT_URL=https://grafana.benlawson.dev
  - GF_SERVER_DOMAIN=grafana.benlawson.dev
networks:
  - proxynet
restart: unless-stopped
```

### Critical Files
- `data/grafana.db` - SQLite database (dashboards, users, settings)
- `data/plugins/` - Installed plugins
- `data/provisioning/` - Auto-provisioned data sources and dashboards

### Default Credentials
- Username: `admin`
- Password: Set via `GRAFANA_PASSWORD` in .env

## Common Tasks

### Restart Grafana
```powershell
cd /mnt/e/Docker/grafana
docker compose restart
```

### View Logs
```powershell
docker logs grafana -f
```

### Backup Grafana
```powershell
# Stop Grafana
docker compose stop

# Backup database and config
tar -czf grafana-backup-$(Get-Date -Format "yyyyMMdd").tar.gz data/

# Start Grafana
docker compose start
```

### Install Plugins
```powershell
# Option 1: Add to environment variable
GF_INSTALL_PLUGINS=plugin-name,another-plugin

# Option 2: Install manually
docker exec grafana grafana-cli plugins install plugin-name
docker compose restart
```

### Reset Admin Password
```powershell
docker exec grafana grafana-cli admin reset-admin-password newpassword
```

## Data Source Configuration

### Add Prometheus Data Source
1. Go to Configuration > Data Sources
2. Click "Add data source"
3. Select "Prometheus"
4. Configure:
   - Name: `Prometheus`
   - URL: `http://prometheus:9090` (internal Docker network)
   - Access: Server (default)
   - Scrape interval: 15s
5. Click "Save & Test"

### Add InfluxDB Data Source
```yaml
Name: InfluxDB
URL: http://influxdb:8086
Database: telegraf  # Or your database name
Access: Server
```

## Dashboard Management

### Importing Community Dashboards
1. Go to Dashboards > Import
2. Enter dashboard ID or paste JSON
3. Select Prometheus data source
4. Click "Import"

### Recommended Dashboard IDs

#### Docker Monitoring
- **893**: Docker container metrics
- **10619**: Docker monitoring (cAdvisor)
- **11600**: Docker & system monitoring

#### Node Exporter (Raspberry Pi)
- **1860**: Node Exporter Full (most popular)
- **10578**: Raspberry Pi Monitoring
- **11074**: Node Exporter for Prometheus Dashboard

#### Prometheus
- **3662**: Prometheus 2.0 Overview
- **6417**: Prometheus Stats

### Creating Custom Dashboards

#### Basic Panel Setup
1. Click "+" > Dashboard > Add new panel
2. Select data source (Prometheus)
3. Enter PromQL query
4. Configure visualization (Graph, Gauge, Stat, etc.)
5. Set panel title and description
6. Save dashboard

#### Example Panel: Container CPU Usage
```promql
rate(container_cpu_usage_seconds_total{name!=""}[5m]) * 100
```
- Visualization: Time series
- Unit: percent (0-100)
- Legend: `{{ name }}`

#### Example Panel: Pi Temperature
```promql
node_hwmon_temp_celsius{instance="raspberry-pi"}
```
- Visualization: Gauge
- Unit: celsius (°C)
- Thresholds: Green (0-60), Yellow (60-70), Red (70+)

## Variables (Template Variables)

### Create Host Variable
1. Dashboard Settings > Variables > Add variable
2. Name: `host`
3. Type: Query
4. Query: `label_values(container_cpu_usage_seconds_total, host)`
5. Use in queries: `{host="$host"}`

### Create Container Variable
```
Name: container
Type: Query
Query: label_values(container_cpu_usage_seconds_total{host="$host"}, name)
Multi-value: true
Include All: true
```

## Integration Points

### Homepage Dashboard
```yaml
- Grafana:
    icon: grafana.png
    href: https://grafana.benlawson.dev
    description: Metrics visualization
```

### SWAG reverse proxy
- Proxy to: `http://grafana:3000`
- SSL: Enabled
- WebSocket: Recommended for live dashboards

### Alerting (Built-in)
Grafana can send alerts via:
- Email
- Slack
- Discord
- PagerDuty
- Webhook

## Alert Configuration

### Create Alert Rule
1. Edit panel > Alert tab
2. Click "Create Alert"
3. Configure conditions:
   - Query: PromQL expression
   - Condition: IS ABOVE, IS BELOW, etc.
   - Threshold: Numeric value
   - For: Duration before firing
4. Configure notifications
5. Save dashboard

### Example: High CPU Alert
```
Query: rate(container_cpu_usage_seconds_total{name="plex"}[5m]) * 100
Condition: IS ABOVE 80
For: 5m
Message: Plex container CPU usage is high
```

### Notification Channels
1. Alerting > Notification channels
2. Click "Add channel"
3. Choose type (Email, Slack, etc.)
4. Configure settings
5. Test notification
6. Save

## Troubleshooting

### Cannot Connect to Prometheus
1. Check data source URL: `http://prometheus:9090`
2. Verify Prometheus container is running: `docker ps`
3. Check both are on proxynet: `docker network inspect proxynet`
4. Test from Grafana container: `docker exec grafana curl http://prometheus:9090/api/v1/status/config`

### Dashboards Not Loading
1. Check browser console for errors
2. Verify data source is configured
3. Test PromQL queries in Prometheus first
4. Check time range selector
5. Review Grafana logs: `docker logs grafana`

### Panels Show "No Data"
1. Verify data source is selected
2. Check time range matches data availability
3. Test query in Prometheus UI
4. Verify metric names are correct
5. Check Prometheus is scraping targets

### High Memory Usage
1. Reduce dashboard refresh rate
2. Limit number of panels per dashboard
3. Use time series limits in queries
4. Clear old sessions: Grafana UI > Server Admin > Sessions

### Slow Dashboard Performance
1. Reduce time range
2. Increase query step interval
3. Use recording rules in Prometheus
4. Simplify complex queries
5. Enable query caching

## Best Practices

1. **Organize Dashboards**: Use folders (Docker, System, Gaming, etc.)
2. **Use Variables**: Make dashboards flexible with template variables
3. **Set Appropriate Refresh**: Don't refresh faster than scrape interval
4. **Add Descriptions**: Document panels and variables
5. **Backup Regularly**: Export dashboards as JSON
6. **Use Annotations**: Mark deployments and incidents
7. **Test Alerts**: Ensure notifications work before relying on them
8. **Mobile-Friendly**: Test dashboards on mobile devices

## Security Considerations

- **Change Default Password**: Immediately after first login
- **Use Strong Passwords**: Store in .env file
- **Enable HTTPS**: Via SWAG reverse proxy
- **Limit Anonymous Access**: Disable if not needed
- **Review User Permissions**: Use Viewer/Editor roles appropriately
- **API Keys**: Use for integrations instead of passwords
- **Audit Logs**: Enable and review regularly

## Performance Tuning

### For Many Dashboards
```yaml
GF_DATABASE_TYPE=mysql  # Switch from SQLite to MySQL for better performance
GF_DATABASE_HOST=mysql:3306
GF_DATABASE_NAME=grafana
GF_DATABASE_USER=grafana
GF_DATABASE_PASSWORD=password
```

### For Heavy Queries
```yaml
GF_DATAPROXY_TIMEOUT=60  # Increase query timeout
GF_DATAPROXY_KEEP_ALIVE_SECONDS=300
```

### Memory Limits
```yaml
deploy:
  resources:
    limits:
      memory: 512M
    reservations:
      memory: 256M
```

## Useful Environment Variables

```yaml
# Security
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
GF_SECURITY_SECRET_KEY=${GRAFANA_SECRET_KEY}

# Server
GF_SERVER_ROOT_URL=https://grafana.benlawson.dev
GF_SERVER_DOMAIN=grafana.benlawson.dev
GF_SERVER_HTTP_PORT=3000

# Anonymous Access (disable for security)
GF_AUTH_ANONYMOUS_ENABLED=false

# Plugins
GF_INSTALL_PLUGINS=plugin1,plugin2,plugin3

# Logging
GF_LOG_LEVEL=info  # debug for troubleshooting

# SMTP (for email alerts)
GF_SMTP_ENABLED=true
GF_SMTP_HOST=smtp.gmail.com:587
GF_SMTP_USER=your-email@gmail.com
GF_SMTP_PASSWORD=app-password
GF_SMTP_FROM_ADDRESS=your-email@gmail.com
```

## Provisioning (Auto-Configuration)

### Auto-Provision Data Sources
Create `data/provisioning/datasources/datasource.yml`:
```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

### Auto-Provision Dashboards
Create `data/provisioning/dashboards/dashboard.yml`:
```yaml
apiVersion: 1

providers:
  - name: 'default'
    folder: ''
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

Then place JSON dashboards in `data/dashboards/`.

## Useful Queries for Home Lab

### Windows Container CPU Usage
```promql
rate(container_cpu_usage_seconds_total{name=~"plex|sonarr|radarr"}[5m]) * 100
```

### Windows Container Memory
```promql
container_memory_usage_bytes{name=~"plex|sonarr|radarr"} / 1024^3
```

### Pi CPU Temperature
```promql
node_hwmon_temp_celsius{instance="raspberry-pi"}
```

### Pi Memory Usage (%)
```promql
(node_memory_MemTotal_bytes{instance="raspberry-pi"} - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100
```

### All Container CPU Usage (Multi-Host)
```promql
rate(container_cpu_usage_seconds_total{name!=""}[5m]) * 100
```

### Disk Space by Host
```promql
(node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100
```

## Plugin Recommendations

### Popular Plugins
- **Clock Panel**: Add clocks to dashboards
- **Pie Chart**: Better pie chart visualization
- **Worldmap Panel**: Geographic data
- **Status Panel**: Status indicators
- **Boom Table**: Advanced table formatting

### Installation
```yaml
GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-piechart-panel,grafana-worldmap-panel
```

Or manually:
```powershell
docker exec grafana grafana-cli plugins install plugin-name
docker compose restart
```

## Sharing Dashboards

### Export Dashboard
1. Dashboard Settings > JSON Model
2. Copy JSON
3. Save to file or share URL

### Import Dashboard
1. Dashboards > Import
2. Paste JSON or upload file
3. Select data source
4. Import

### Snapshot (Public Sharing)
1. Dashboard > Share > Snapshot
2. Set expiration time
3. Copy snapshot URL
4. Share with anyone (read-only)

## Multi-User Setup

### Create Users
1. Server Admin > Users
2. Click "New user"
3. Set username, email, password
4. Assign role (Viewer, Editor, Admin)

### Roles
- **Viewer**: Read-only access to dashboards
- **Editor**: Can edit dashboards and alerts
- **Admin**: Full administrative access

### Organizations (Optional)
For separating environments (prod, staging, dev):
1. Server Admin > Orgs
2. Create new organization
3. Assign users to organizations
4. Each org has separate dashboards and data sources

## Backup and Restore

### Manual Backup
```powershell
# Stop Grafana
docker compose stop

# Backup data directory
tar -czf grafana-backup-$(Get-Date -Format "yyyyMMdd").tar.gz data/

# Start Grafana
docker compose start
```

### Export All Dashboards
```powershell
# Using Grafana API
$dashboards = curl -u admin:password http://localhost:3000/api/search?query=&
foreach ($dashboard in $dashboards | ConvertFrom-Json) {
    $json = curl -u admin:password "http://localhost:3000/api/dashboards/uid/$($dashboard.uid)"
    $json | Out-File "dashboard-$($dashboard.uid).json"
}
```

### Restore Dashboards
1. Import each JSON file via UI
2. Or use provisioning to auto-import on startup

## Monitoring Grafana Itself

### Health Check
```powershell
curl http://localhost:3000/api/health
```

### Metrics Endpoint (Enable in Config)
```yaml
GF_METRICS_ENABLED=true
```
Then scrape with Prometheus: `http://grafana:3000/metrics`

## Common Dashboard Layouts

### Overview Dashboard
- Row 1: Total containers, CPU usage, Memory usage, Disk space
- Row 2: Container CPU graph (all containers)
- Row 3: Container Memory graph (all containers)
- Row 4: Network traffic (in/out)

### Pi-Specific Dashboard
- Row 1: CPU temp gauge, Memory usage gauge, Disk space gauge, Uptime stat
- Row 2: CPU usage graph per core
- Row 3: Memory usage over time
- Row 4: Network traffic, Disk I/O

### Service-Specific Dashboard (e.g., Plex)
- CPU usage, Memory usage, Disk usage
- Network traffic (streaming bandwidth)
- Active streams (if metrics available)
- Transcoding sessions

This multi-tier architecture (Prometheus → Grafana) provides powerful monitoring across all hosts in your home lab.
