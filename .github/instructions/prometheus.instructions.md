---
applyTo: "prometheus/**"
---

# Prometheus Expert Instructions

You are an expert in Prometheus time-series database and monitoring system configuration.

## Service Overview
Prometheus scrapes metrics from various exporters (cAdvisor, node-exporter) and stores them as time-series data. It's the core of the monitoring stack, feeding data to Grafana dashboards.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "9090:9090"
volumes:
  - ./config:/etc/prometheus
  - ./data:/prometheus
command:
  - '--config.file=/etc/prometheus/prometheus.yml'
  - '--storage.tsdb.path=/prometheus'
  - '--web.console.libraries=/usr/share/prometheus/console_libraries'
  - '--web.console.templates=/usr/share/prometheus/consoles'
  - '--storage.tsdb.retention.time=30d'
  - '--web.enable-lifecycle'
networks:
  - proxynet
restart: unless-stopped
```

### Critical Files
- `config/prometheus.yml` - Main configuration (scrape targets, jobs)
- `config/alerts.yml` - Alert rules (optional)
- `data/` - Time-series database (TSDB) storage

### Default Ports
- 9090 - Web UI and API

## Configuration Structure

### prometheus.yml Anatomy
```yaml
global:
  scrape_interval: 15s  # Default scrape frequency
  evaluation_interval: 15s  # Rule evaluation frequency

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']
    scrape_interval: 30s

  - job_name: 'cadvisor-pi'
    static_configs:
      - targets: ['192.168.50.41:8080']
        labels:
          instance: 'raspberry-pi'
          host: 'pi3'
    scrape_interval: 30s

  - job_name: 'node-exporter-pi'
    static_configs:
      - targets: ['192.168.50.41:9100']
        labels:
          instance: 'raspberry-pi'
          host: 'pi3'
    scrape_interval: 15s
```

## Common Tasks

### Reload Configuration (Without Restart)
```powershell
# Use web.enable-lifecycle flag
curl -X POST http://localhost:9090/-/reload
```

### Restart Prometheus
```powershell
cd E:\Docker\prometheus
docker compose restart
```

### Validate Configuration
```powershell
# Check syntax before reload
docker run --rm -v E:\Docker\prometheus\config:/config prom/prometheus:latest promtool check config /config/prometheus.yml
```

### View Logs
```powershell
docker logs prometheus -f
```

### Check Targets Status
- Web UI: http://localhost:9090/targets
- Shows which exporters are UP/DOWN

### Query Metrics
- Web UI: http://localhost:9090/graph
- PromQL queries to test data collection

## Adding New Scrape Targets

### For Docker Services (Same Host)
```yaml
- job_name: 'service-name'
  static_configs:
    - targets: ['container_name:port']
  scrape_interval: 30s
```

### For Remote Services (Pi, etc.)
```yaml
- job_name: 'service-name-remote'
  static_configs:
    - targets: ['192.168.50.XX:port']
      labels:
        instance: 'descriptive-name'
        host: 'hostname'
  scrape_interval: 15s
```

### With Authentication
```yaml
- job_name: 'secured-service'
  static_configs:
    - targets: ['service:port']
  basic_auth:
    username: 'user'
    password: 'pass'
```

## Integration Points

### Grafana Data Source
- URL: `http://prometheus:9090` (internal Docker network)
- Access: Server (default)
- No authentication required

### Homepage Dashboard
```yaml
- Prometheus:
    icon: prometheus.png
    href: https://prometheus.benlawson.dev
    description: Metrics collection
    widget:
      type: prometheus
      url: http://prometheus:9090
```

### Alert Manager (Optional)
```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093
```

## PromQL Query Examples

### Container CPU Usage
```promql
rate(container_cpu_usage_seconds_total{name!=""}[5m]) * 100
```

### Container Memory Usage
```promql
container_memory_usage_bytes{name!=""} / 1024^3  # GB
```

### Pi CPU Temperature
```promql
node_hwmon_temp_celsius{instance="raspberry-pi"}
```

### Pi Memory Available
```promql
node_memory_MemAvailable_bytes{instance="raspberry-pi"} / 1024^3  # GB
```

### Disk Space Free (%)
```promql
node_filesystem_avail_bytes / node_filesystem_size_bytes * 100
```

### Network Traffic (MB/s)
```promql
rate(node_network_receive_bytes_total[5m]) / 1024^2
```

## Troubleshooting

### Target Shows DOWN
1. Check if exporter container is running: `docker ps`
2. Test connectivity: `curl http://target:port/metrics`
3. Check Prometheus logs: `docker logs prometheus`
4. Verify network connectivity (proxynet for Docker, IP for remote)
5. Check firewall rules for remote targets

### Configuration Reload Fails
1. Validate config: `promtool check config prometheus.yml`
2. Check for YAML syntax errors
3. Ensure web.enable-lifecycle flag is set
4. Restart instead: `docker compose restart`

### High Disk Usage
1. Check TSDB size: `du -sh E:\Docker\prometheus\data`
2. Reduce retention time: `--storage.tsdb.retention.time=15d`
3. Reduce scrape frequency for high-cardinality metrics
4. Consider metric relabeling to drop unused metrics

### High Memory Usage
1. Reduce scrape targets or frequency
2. Drop high-cardinality metrics (container IDs, etc.)
3. Increase scrape_interval for heavy exporters
4. Use recording rules for frequently queried metrics

### Queries Timing Out
1. Reduce query time range
2. Use recording rules for expensive queries
3. Increase step interval in queries
4. Check TSDB for corruption: `promtool tsdb analyze data/`

## Best Practices

1. **Label Consistently**: Use standard labels (instance, job, host)
2. **Scrape Intervals**: Match exporter capabilities (30s for cAdvisor, 15s for node-exporter)
3. **Retention Time**: Balance storage vs. historical data needs (default: 15d, we use 30d)
4. **Backup Config**: Keep prometheus.yml in git
5. **Test Changes**: Use promtool to validate before reload
6. **Monitor Prometheus**: Check /metrics endpoint for self-monitoring
7. **Use Recording Rules**: Pre-compute expensive queries
8. **Relabeling**: Drop unnecessary labels to reduce cardinality

## Security Considerations

- **No Authentication by Default**: Add reverse proxy with auth for external access
- **Sensitive Data**: Metrics may contain hostnames, IPs, paths
- **Network Isolation**: Keep on proxynet, expose via NPM with auth
- **Config Exposure**: Don't commit passwords in prometheus.yml (use Docker secrets)
- **Web UI Access**: Restrict to trusted networks only

## Performance Tuning

### For Large Deployments
```yaml
# Increase WAL compression
--storage.tsdb.wal-compression

# Adjust memory limits
--storage.tsdb.max-block-duration=2h
--storage.tsdb.min-block-duration=2h
```

### For Resource-Constrained Systems
```yaml
# Reduce retention
--storage.tsdb.retention.time=7d

# Increase scrape intervals
scrape_interval: 60s

# Limit concurrent scrapes
scrape_interval: 30s
scrape_timeout: 10s
```

## Recording Rules (Advanced)

Create `config/recording_rules.yml`:
```yaml
groups:
  - name: docker_rules
    interval: 30s
    rules:
      - record: container_cpu_usage_percent
        expr: rate(container_cpu_usage_seconds_total[5m]) * 100

      - record: container_memory_usage_gb
        expr: container_memory_usage_bytes / 1024^3
```

Add to prometheus.yml:
```yaml
rule_files:
  - 'recording_rules.yml'
```

## Alert Rules (Advanced)

Create `config/alerts.yml`:
```yaml
groups:
  - name: host_alerts
    rules:
      - alert: HighCPUUsage
        expr: container_cpu_usage_percent > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Container {{ $labels.name }} high CPU usage"

      - alert: PiHighTemperature
        expr: node_hwmon_temp_celsius{instance="raspberry-pi"} > 70
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Pi CPU temperature is {{ $value }}°C"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Disk space low on {{ $labels.instance }}"
```

## Monitoring Prometheus Itself

### Key Metrics
```promql
# Scrape duration
scrape_duration_seconds

# Samples ingested per second
rate(prometheus_tsdb_head_samples_appended_total[5m])

# Active time series
prometheus_tsdb_head_series

# WAL size
prometheus_tsdb_wal_storage_size_bytes / 1024^3  # GB

# TSDB size
prometheus_tsdb_storage_blocks_bytes / 1024^3  # GB
```

### Health Check
```powershell
curl http://localhost:9090/-/healthy
curl http://localhost:9090/-/ready
```

## Backup and Restore

### Backup Prometheus Data
```powershell
# Stop Prometheus
docker compose stop

# Backup data directory
tar -czf prometheus-backup-$(Get-Date -Format "yyyyMMdd").tar.gz data/

# Start Prometheus
docker compose start
```

### Backup Configuration Only
```powershell
tar -czf prometheus-config-$(Get-Date -Format "yyyyMMdd").tar.gz config/
```

### Restore from Backup
```powershell
# Stop Prometheus
docker compose stop

# Restore data
tar -xzf prometheus-backup-YYYYMMDD.tar.gz

# Start Prometheus
docker compose start
```

## Remote Write (Optional)

For long-term storage or multi-cluster setups:
```yaml
remote_write:
  - url: "http://remote-storage:9009/api/v1/push"
    basic_auth:
      username: 'user'
      password: 'pass'
```

## Federation (Optional)

To scrape metrics from another Prometheus:
```yaml
- job_name: 'federate'
  scrape_interval: 15s
  honor_labels: true
  metrics_path: '/federate'
  params:
    'match[]':
      - '{job="prometheus"}'
      - '{__name__=~"job:.*"}'
  static_configs:
    - targets:
        - 'other-prometheus:9090'
```

## Common Errors and Solutions

### "context deadline exceeded"
- Increase scrape_timeout
- Check exporter response time
- Reduce metric cardinality

### "out of memory"
- Reduce retention time
- Increase Docker memory limits
- Drop high-cardinality metrics

### "too many open files"
- Increase ulimit in Docker
- Reduce number of scrape targets
- Compact TSDB blocks

### "failed to reload config"
- Validate YAML syntax
- Check file permissions
- Review Prometheus logs for specific error

## Useful Prometheus Flags

```bash
--config.file=/etc/prometheus/prometheus.yml  # Config location
--storage.tsdb.path=/prometheus  # Data directory
--storage.tsdb.retention.time=30d  # How long to keep data
--storage.tsdb.retention.size=50GB  # Max storage size
--web.enable-lifecycle  # Allow config reload via HTTP
--web.external-url=https://prometheus.benlawson.dev  # For alerts/links
--web.enable-admin-api  # Enable admin APIs (dangerous)
--log.level=debug  # Increase logging verbosity
```

## Multi-Host Monitoring Architecture

Current setup:
- **Windows Host**: Prometheus, Grafana, cAdvisor, InfluxDB
- **Raspberry Pi**: cAdvisor, node-exporter, Homebridge, Pi-hole
- **Scraping**: Windows Prometheus scrapes both Windows and Pi exporters
- **Visualization**: Grafana on Windows shows metrics from both hosts

This centralized architecture simplifies management and provides unified dashboards.
