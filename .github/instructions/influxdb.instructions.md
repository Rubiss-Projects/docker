---
applyTo: "influxdb/**"
---

# InfluxDB Expert Instructions

You are an expert in InfluxDB time-series database configuration and management.

## Service Overview
InfluxDB is a high-performance time-series database designed for storing and querying metrics, events, and analytics data. In this homelab, it stores monitoring data from various sources including network performance, system metrics, and application statistics.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "8086:8086"
environment:
  - DOCKER_INFLUXDB_INIT_MODE=setup
  - DOCKER_INFLUXDB_INIT_USERNAME=admin
  - DOCKER_INFLUXDB_INIT_PASSWORD=secure_password
  - DOCKER_INFLUXDB_INIT_ORG=homelab
  - DOCKER_INFLUXDB_INIT_BUCKET=metrics
  - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=your-super-secret-token
volumes:
  - ./data:/var/lib/influxdb2
  - ./config:/etc/influxdb2
restart: unless-stopped
```

### Critical Files
- `data/influxd.bolt` - Metadata database
- `data/engine/` - Time-series data storage
- `config/config.yml` - InfluxDB configuration (optional)

### Default Port
- 8086 - HTTP API and UI

## Common Tasks

### First-Time Setup
1. Start container with INIT environment variables
2. Access UI: `http://localhost:8086`
3. Login with admin credentials
4. Create additional buckets and tokens as needed

### Create Bucket
UI: Data > Buckets > Create Bucket
- Name: `speedtest`
- Retention: 90 days (or infinite)

CLI:
```powershell
docker exec influxdb influx bucket create -n speedtest -o homelab -r 90d -t your-admin-token
```

### Create API Token
UI: Data > API Tokens > Generate API Token
- Read/Write Token: Select buckets
- All Access Token: Full access

CLI:
```powershell
docker exec influxdb influx auth create --org homelab --read-buckets --write-buckets -t your-admin-token
```

### Write Data (Line Protocol)
```powershell
$data = "measurement,tag1=value1 field1=100 $(([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) * 1000000000)"

$headers = @{
    "Authorization" = "Token your-token"
    "Content-Type" = "text/plain; charset=utf-8"
}

Invoke-RestMethod -Uri "http://localhost:8086/api/v2/write?org=homelab&bucket=metrics&precision=ns" -Method Post -Headers $headers -Body $data
```

### Query Data (Flux)
UI: Data Explorer > Script Editor
```flux
from(bucket: "metrics")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "cpu")
  |> filter(fn: (r) => r._field == "usage_percent")
  |> aggregateWindow(every: 1m, fn: mean)
```

API:
```powershell
$query = @"
from(bucket: "metrics")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "cpu")
"@

$body = @{
    query = $query
    type = "flux"
} | ConvertTo-Json

$headers = @{
    "Authorization" = "Token your-token"
    "Content-Type" = "application/json"
}

Invoke-RestMethod -Uri "http://localhost:8086/api/v2/query?org=homelab" -Method Post -Headers $headers -Body $body
```

### Delete Data
```flux
from(bucket: "metrics")
  |> range(start: 2024-01-01T00:00:00Z, stop: 2024-01-31T23:59:59Z)
  |> filter(fn: (r) => r._measurement == "old_measurement")
  |> drop()
```

Or via API with predicate:
```powershell
$body = @{
    start = "2024-01-01T00:00:00Z"
    stop = "2024-01-31T23:59:59Z"
    predicate = "_measurement='old_measurement'"
} | ConvertTo-Json

$headers = @{
    "Authorization" = "Token your-token"
    "Content-Type" = "application/json"
}

Invoke-RestMethod -Uri "http://localhost:8086/api/v2/delete?org=homelab&bucket=metrics" -Method Post -Headers $headers -Body $body
```

## Integration Points

### Grafana Data Source
Grafana > Configuration > Data Sources > Add InfluxDB:
- Query Language: Flux
- URL: `http://influxdb:8086`
- Organization: homelab
- Token: (API token with read access)
- Default Bucket: metrics

### Telegraf (Metrics Collection)
Telegraf config:
```toml
[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8086"]
  token = "your-token"
  organization = "homelab"
  bucket = "metrics"
```

### Prometheus (via Telegraf)
Telegraf can scrape Prometheus metrics and write to InfluxDB.

### Homepage Dashboard
```yaml
- InfluxDB:
    icon: influxdb.png
    href: http://localhost:8086
    description: Time-series database
```

### SWAG reverse proxy
```
Domain: influxdb.benlawson.dev
Forward: http://influxdb:8086
SSL: Let's Encrypt
```

## Troubleshooting

### Cannot Access UI
1. Check container: `docker ps`
2. Test port: `curl http://localhost:8086/health`
3. Review logs: `docker logs influxdb`
4. Verify port 8086 not in use

### Authentication Errors
1. Verify token is correct
2. Check token permissions for bucket
3. Ensure org name is correct
4. Re-create token if needed

### High Memory Usage
1. Check cardinality: `influx query "from(bucket:'metrics') |> group() |> count()"`
2. Reduce retention periods
3. Compact shards: automatic, but can force
4. Increase memory limit if needed

### Write Errors
1. Check line protocol syntax
2. Verify bucket exists
3. Check token has write permission
4. Review API error response

### Slow Queries
1. Add time range filter: `range(start: -1h)`
2. Use aggregateWindow to downsample
3. Avoid unbounded queries
4. Check indexes and cardinality
5. Monitor query execution time

## Best Practices

1. **Bucket Retention**: Set appropriate retention policies (30d, 90d, 1y)
2. **API Tokens**: Use scoped tokens (not all-access)
3. **Downsampling**: Use tasks to downsample old data
4. **Cardinality**: Limit high-cardinality tags
5. **Measurement Naming**: Consistent naming conventions
6. **Backups**: Regular backups of bolt file and data
7. **Monitoring**: Monitor InfluxDB itself with Telegraf

## Security Considerations

- **Admin Token**: Protect admin token (full access)
- **API Tokens**: Scope to minimum required permissions
- **HTTPS**: Use reverse proxy for SSL
- **Network**: Don't expose 8086 publicly without auth
- **Credentials**: Rotate tokens periodically
- **Bucket Access**: Limit read/write by token

## Advanced Configuration

### Retention Policies (Buckets)
Different retention for different data:
- `metrics_realtime` - 7 days (high resolution)
- `metrics_hourly` - 90 days (downsampled)
- `metrics_daily` - 1 year (aggregated)

### Downsampling Task
Create task to downsample data:
```flux
option task = {name: "downsample-cpu", every: 1h}

from(bucket: "metrics_realtime")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "cpu")
  |> aggregateWindow(every: 5m, fn: mean)
  |> to(bucket: "metrics_hourly")
```

### Alerts (via Tasks + HTTP)
```flux
option task = {name: "high-cpu-alert", every: 5m}

from(bucket: "metrics")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "cpu" and r._field == "usage_percent")
  |> mean()
  |> filter(fn: (r) => r._value > 90)
  |> map(fn: (r) => ({r with _value: "CPU usage: ${r._value}%"}))
  |> http.post(url: "https://discord.com/api/webhooks/...")
```

### Continuous Queries (Tasks)
Flux tasks replace InfluxDB 1.x continuous queries:
```flux
option task = {name: "aggregate-metrics", every: 1h}

from(bucket: "metrics")
  |> range(start: -1h)
  |> aggregateWindow(every: 1m, fn: mean)
  |> to(bucket: "metrics_aggregated")
```

## Monitoring InfluxDB

### System Monitoring
InfluxDB exposes internal metrics:
```flux
from(bucket: "_monitoring")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "influxdb_database")
```

### Health Endpoint
```powershell
Invoke-RestMethod -Uri "http://localhost:8086/health"
```

Response:
```json
{
  "name": "influxdb",
  "message": "ready for queries and writes",
  "status": "pass",
  "checks": [],
  "version": "2.7.4",
  "commit": "a01..."
}
```

### Cardinality Check
```flux
import "influxdata/influxdb/schema"

schema.measurements(bucket: "metrics")
  |> map(fn: (r) => ({measurement: r._value}))
```

## Backup and Restore

### Backup (Full)
```powershell
docker compose stop
tar -czf "influxdb-backup-$(Get-Date -Format 'yyyyMMdd').tar.gz" data/
docker compose start
```

### Backup (CLI - Recommended)
```powershell
docker exec influxdb influx backup /tmp/backup -t your-admin-token
docker cp influxdb:/tmp/backup ./influxdb-backup
```

### Restore
```powershell
docker compose stop
docker cp ./influxdb-backup influxdb:/tmp/backup
docker exec influxdb influx restore /tmp/backup
docker compose start
```

## CLI Usage

### Bucket Management
```powershell
# List buckets
docker exec influxdb influx bucket list -t your-token

# Create bucket
docker exec influxdb influx bucket create -n new_bucket -o homelab -r 30d -t your-token

# Delete bucket
docker exec influxdb influx bucket delete -i bucket_id -t your-token
```

### Token Management
```powershell
# List tokens
docker exec influxdb influx auth list -t your-token

# Create read token
docker exec influxdb influx auth create --read-bucket bucket_id -o homelab -t your-token

# Delete token
docker exec influxdb influx auth delete --id token_id -t your-token
```

### User Management
```powershell
# List users
docker exec influxdb influx user list -t your-token

# Create user
docker exec influxdb influx user create -n username -o homelab -t your-token

# Update password
docker exec influxdb influx user password -n username -t your-token
```

## Flux Query Examples

### Basic Query
```flux
from(bucket: "metrics")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "cpu")
  |> filter(fn: (r) => r._field == "usage_percent")
```

### Aggregation
```flux
from(bucket: "metrics")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "mem")
  |> aggregateWindow(every: 1h, fn: mean)
```

### Join Multiple Measurements
```flux
cpu = from(bucket: "metrics")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "cpu")

mem = from(bucket: "metrics")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "mem")

join(tables: {cpu: cpu, mem: mem}, on: ["_time", "host"])
```

### Calculate Derivative (Rate of Change)
```flux
from(bucket: "metrics")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "net" and r._field == "bytes_sent")
  |> derivative(unit: 1s, nonNegative: true)
```

## Performance Optimization

### Compaction
InfluxDB automatically compacts shards. Monitor:
```flux
from(bucket: "_monitoring")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "storage_compactions_queued")
```

### Cache Size
Increase cache for write-heavy workloads:
```yaml
# config/config.yml
storage-cache-max-memory-size: 1GB
storage-cache-snapshot-memory-size: 256MB
```

### Shard Duration
For high-frequency writes, adjust shard duration (default: 1 week).

This powerful time-series database provides high-performance storage and querying for metrics, events, and analytics across the homelab monitoring infrastructure.
