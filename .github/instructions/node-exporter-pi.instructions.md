---
applyTo: "pi/node-exporter/**"
---

# Node Exporter (Raspberry Pi) Expert Instructions

You are an expert in Prometheus Node Exporter for system-level metrics on Raspberry Pi.

## Service Overview
Node Exporter collects hardware and OS-level metrics from the Raspberry Pi, including CPU, memory, disk, temperature, and network stats. It's the primary source for system monitoring.

## Technical Configuration

### Docker Compose Patterns
```yaml
network_mode: host  # REQUIRED for accurate network and system metrics
volumes:
  - /proc:/host/proc:ro
  - /sys:/host/sys:ro
  - /:/rootfs:ro
command:
  - '--path.procfs=/host/proc'
  - '--path.sysfs=/host/sys'
  - '--path.rootfs=/rootfs'
  - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
  - '--collector.netclass.ignored-devices=^(veth.*|br-.*|docker.*)$$'
  - '--collector.netdev.device-exclude=^(veth.*|br-.*|docker.*)$$'
restart: unless-stopped
```

### Critical Requirements
- **MUST** use `network_mode: host` for accurate network metrics
- All volumes must be read-only (`:ro`)
- Path remapping required for `/proc` and `/sys`

### Default Port
- Runs on port 9100 (standard Prometheus node_exporter port)
- No port mapping needed due to host networking

## Metrics Collected

### System Metrics
- **CPU**: Usage per core, frequency, temperature
- **Memory**: Total, used, free, cached, swap
- **Disk**: Space, I/O operations, read/write bytes
- **Load**: 1m, 5m, 15m load averages
- **Uptime**: System boot time and uptime

### Network Metrics
- **Interfaces**: RX/TX bytes, packets, errors, drops
- **TCP/UDP**: Connection states, segments sent/received
- **Exclude**: Docker bridges and virtual interfaces (veth, br-)

### Hardware Metrics (Raspberry Pi Specific)
- **Temperature**: CPU/GPU temperature (`/sys/class/thermal/`)
- **Throttling**: CPU frequency throttling status
- **Voltage**: Under-voltage detection

### Filesystem Metrics
- **Mountpoints**: Disk usage, inodes
- **Excludes**: Virtual filesystems (sys, proc, dev, docker)

## Common Tasks

### Viewing Metrics
```bash
# Web interface (basic)
curl http://192.168.50.41:9100/metrics

# Specific metric
curl -s http://192.168.50.41:9100/metrics | grep 'node_cpu'

# Temperature
curl -s http://192.168.50.41:9100/metrics | grep 'node_hwmon_temp_celsius'
```

### Viewing Logs
```bash
docker logs node-exporter -f
```

### Testing Prometheus Scrape
```bash
# From Windows host
curl http://192.168.50.41:9100/metrics | head -n 50
```

### Checking Resource Usage
```bash
docker stats node-exporter
# Should be ~10-15MB RAM, minimal CPU
```

## Integration Points

### Prometheus Scraping
Windows Prometheus scrapes node-exporter:
```yaml
# In prometheus.yml
- job_name: 'node-exporter-pi'
  static_configs:
    - targets: ['192.168.50.41:9100']
      labels:
        instance: 'raspberry-pi'
        host: 'pi3'
  scrape_interval: 15s  # Can be more frequent than cAdvisor
```

### Grafana Dashboards
Recommended dashboards:
- **1860**: Node Exporter Full (most popular, comprehensive)
- **10578**: Raspberry Pi Monitoring (Pi-specific)
- **11074**: Node Exporter for Prometheus Dashboard (detailed)

Key panels to include:
- CPU usage and temperature
- Memory usage (with swap)
- Disk space and I/O
- Network traffic
- System load and uptime

### Homepage Dashboard
```yaml
- Pi System Monitor:
    icon: prometheus.png
    href: http://192.168.50.41:9100/metrics
    description: System metrics (Node Exporter)
```

### Alerting Examples
```yaml
# CPU temperature alert
- alert: HighCPUTemperature
  expr: node_hwmon_temp_celsius{instance="raspberry-pi"} > 70
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Pi CPU temperature is high"

# Disk space alert
- alert: DiskSpaceLow
  expr: node_filesystem_avail_bytes{instance="raspberry-pi",mountpoint="/"} / node_filesystem_size_bytes < 0.1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Pi disk space below 10%"

# Memory pressure
- alert: HighMemoryUsage
  expr: (node_memory_MemTotal_bytes{instance="raspberry-pi"} - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.9
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Pi memory usage above 90%"
```

## Troubleshooting

### No Metrics Returned
1. Verify container is running: `docker ps | grep node-exporter`
2. Check host networking: `docker inspect node-exporter | grep NetworkMode`
3. Test endpoint: `curl http://192.168.50.41:9100/metrics`
4. Review logs: `docker logs node-exporter`

### Missing Temperature Metrics
1. Check thermal zone paths: `ls /sys/class/thermal/`
2. Verify `/sys` volume mount exists
3. Look for `node_hwmon_temp_celsius` metric
4. Pi 3 typically exposes thermal_zone0 (CPU/GPU)

### Incorrect Network Stats
1. Ensure `network_mode: host` is set
2. Verify device exclusions are working (no docker interfaces)
3. Check for errors in logs
4. Test: `curl -s http://192.168.50.41:9100/metrics | grep node_network_receive_bytes_total`

### Filesystem Metrics Missing
1. Check rootfs mount: `/:/rootfs:ro`
2. Verify mount point exclusions
3. Look for `node_filesystem_avail_bytes` metric
4. Check permissions on mounted paths

## Best Practices

1. **Use Host Networking**: Essential for accurate system metrics
2. **Keep Updated**: Watchtower auto-updates to latest stable
3. **Monitor Temperature**: Pi 3 can throttle at 80°C
4. **Disk Monitoring**: Watch SD card usage (limited lifespan)
5. **Lightweight**: node-exporter uses ~15MB RAM, very efficient

## Raspberry Pi 3 Specific Metrics

### Temperature Monitoring
```promql
# CPU temperature in Celsius
node_hwmon_temp_celsius{instance="raspberry-pi"}

# Temperature in Fahrenheit
node_hwmon_temp_celsius{instance="raspberry-pi"} * 9/5 + 32
```

### CPU Frequency and Throttling
```promql
# Current CPU frequency (Hz)
node_cpu_frequency_hertz{instance="raspberry-pi"}

# Check for throttling (Pi-specific)
# Look for sysfs files: /sys/devices/system/cpu/cpu*/cpufreq/
```

### Memory Usage (1GB Total)
```promql
# Available memory in GB
node_memory_MemAvailable_bytes{instance="raspberry-pi"} / 1024^3

# Memory usage percentage
(node_memory_MemTotal_bytes{instance="raspberry-pi"} - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100
```

### SD Card Health
```promql
# Root filesystem usage
node_filesystem_avail_bytes{instance="raspberry-pi",mountpoint="/"} / 1024^3

# Disk I/O (writes are concern for SD card lifespan)
rate(node_disk_written_bytes_total{instance="raspberry-pi"}[5m])
```

## Security Considerations

- **Read-Only Mounts**: All volumes are read-only
- **No Authentication**: Metrics endpoint is unauthenticated
- **Local Network Only**: Don't expose to internet
- **Sensitive Data**: Metrics may reveal system information
- **Host Networking**: Container has direct host network access

## Performance Impact

### Expected Resource Usage
- **RAM**: 10-15MB
- **CPU**: <2% average
- **Disk I/O**: Minimal (reading sysfs/procfs)
- **Network**: ~50KB per scrape (uncompressed)

### Scrape Frequency
- Recommended: 15s (more frequent than cAdvisor)
- Minimum: 5s (for detailed monitoring)
- Maximum: 60s (for resource-constrained setups)

## Advanced Configuration

### Enable Additional Collectors
```bash
command:
  - '--collector.systemd'  # Systemd service metrics
  - '--collector.processes'  # Process count
  - '--collector.interrupts'  # System interrupts
```

### Disable Unwanted Collectors
```bash
command:
  - '--no-collector.arp'  # Disable ARP table
  - '--no-collector.hwmon'  # Disable hardware monitoring (temperature)
  - '--no-collector.nfs'  # Disable NFS stats
```

### Custom Textfile Collector
```bash
# Create custom metrics
volumes:
  - ./textfile_collector:/textfile_collector:ro
command:
  - '--collector.textfile.directory=/textfile_collector'
```

## Useful Prometheus Queries

### CPU Usage (Per Core)
```promql
rate(node_cpu_seconds_total{instance="raspberry-pi",mode!="idle"}[5m])
```

### Total CPU Usage (%)
```promql
(1 - avg(rate(node_cpu_seconds_total{instance="raspberry-pi",mode="idle"}[5m]))) * 100
```

### Memory Available (GB)
```promql
node_memory_MemAvailable_bytes{instance="raspberry-pi"} / 1024^3
```

### Disk Space Free (%)
```promql
node_filesystem_avail_bytes{instance="raspberry-pi",mountpoint="/"} / node_filesystem_size_bytes * 100
```

### Network Traffic (MB/s)
```promql
rate(node_network_receive_bytes_total{instance="raspberry-pi",device="eth0"}[5m]) / 1024^2
```

### System Load (1m average)
```promql
node_load1{instance="raspberry-pi"}
```

### System Uptime (Days)
```promql
(time() - node_boot_time_seconds{instance="raspberry-pi"}) / 86400
```

## Comparison with Glances

| Feature | Node Exporter | Glances |
|---------|---------------|---------|
| RAM Usage | ~15MB | ~40MB |
| Format | Prometheus native | JSON/Web UI |
| Integration | Prometheus/Grafana | Standalone web UI |
| Metrics Depth | Deep system metrics | High-level overview |
| ARM Performance | Excellent | Good |
| Visualization | Grafana dashboards | Built-in web UI |

**Recommendation**: Use node-exporter with Grafana for better resource usage and integration with existing monitoring stack.

## Monitoring Node Exporter Itself

### Health Check
```bash
curl http://192.168.50.41:9100/
# Should return HTML page with links
```

### Scrape Duration
```promql
scrape_duration_seconds{instance="raspberry-pi",job="node-exporter-pi"}
```

### Metric Count
```bash
curl -s http://192.168.50.41:9100/metrics | grep -c '^node_'
# Typical: 300-500 metrics
```

## When to Adjust Configuration

### Add More Collectors
If you need systemd or process metrics:
```bash
--collector.systemd
--collector.processes
```

### Reduce Metrics
If scrape duration is too long:
```bash
--no-collector.arp
--no-collector.sockstat
--no-collector.netstat
```

### Custom Metrics
For application-specific metrics:
```bash
# Use textfile collector
echo 'custom_metric 123' > /path/to/textfile_collector/custom.prom
```
