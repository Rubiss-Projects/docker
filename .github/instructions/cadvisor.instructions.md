---
applyTo: "{pi/cadvisor/**,cadvisor/**}"
---

# cAdvisor Expert Instructions

You are an expert in cAdvisor container metrics collection for both Raspberry Pi and Windows hosts.

## Service Overview
cAdvisor (Container Advisor) collects, processes, and exports metrics for running containers. 

**Configuration varies by host**:
- **Raspberry Pi 3**: Optimized for limited resources (1GB RAM) with disabled metrics and longer intervals
- **Windows Host**: Standard configuration with full metrics collection for comprehensive monitoring

## Technical Configuration

### Docker Compose Patterns

**Raspberry Pi (Optimized for 1GB RAM)**:
```yaml
ports:
  - "8080:8080"
volumes:
  - /:/rootfs:ro
  - /var/run:/var/run:ro
  - /sys:/sys:ro
  - /var/lib/docker/:/var/lib/docker:ro
  - /dev/disk:/dev/disk:ro
command:
  - --port=8080
  - --docker_only=true
  - --housekeeping_interval=30s
  - --max_housekeeping_interval=60s
  - --disable_metrics=disk,diskIO,network,tcp,udp,percpu,sched,process
  - --storage_duration=2m0s
privileged: true  # Required for full system metrics
restart: unless-stopped
```

**Windows Host (Full Metrics)**:
```yaml
ports:
  - "8081:8080"  # Different port to avoid conflict
volumes:
  - /:/rootfs:ro
  - /var/run:/var/run:ro
  - /sys:/sys:ro
  - /var/lib/docker/:/var/lib/docker:ro
  - /dev/disk:/dev/disk:ro
command:
  - --port=8080
  - --docker_only=true
  - --housekeeping_interval=10s  # More frequent for production
  - --max_housekeeping_interval=35s
  - --storage_duration=2m0s
privileged: true
restart: unless-stopped
```

### Critical Volume Mounts
All volumes are read-only except `/var/run`:
- `/rootfs` - Root filesystem (for host metrics)
- `/var/run` - Docker socket and runtime info
- `/sys` - System information
- `/var/lib/docker` - Docker container data
- `/dev/disk` - Disk statistics

### Raspberry Pi Optimizations

#### Disabled Metrics (Resource Saving)
```bash
--disable_metrics=disk,diskIO,network,tcp,udp,percpu,sched,process
```
These are disabled because:
- `disk/diskIO` - Already covered by node-exporter
- `network/tcp/udp` - Not needed for container-level monitoring
- `percpu` - Redundant with overall CPU metrics on 4-core Pi
- `sched/process` - Too granular for our use case

#### Housekeeping Intervals
```bash
--housekeeping_interval=30s  # Default: 10s (too frequent for Pi)
--max_housekeeping_interval=60s  # Reduce metric collection frequency
```
Longer intervals reduce CPU usage at cost of slightly delayed metrics.

#### Storage Duration
```bash
--storage_duration=2m0s  # Keep only 2 minutes of history
```
Reduces memory usage (default: 5m). Prometheus scrapes every 30s, so 2m is sufficient.

## Common Tasks

### Viewing Web UI
```bash
# Raspberry Pi: http://192.168.50.216:8080
# Windows Server: http://192.168.50.40:8081
# Shows: Container list, resource usage, graphs
```

### Viewing Logs
```bash
# Run from the host where cAdvisor is running
docker logs cadvisor -f
```

### Testing Prometheus Scrape
```bash
# Raspberry Pi
curl http://192.168.50.216:8080/metrics

# Windows Server
curl http://192.168.50.40:8081/metrics
```

### Checking Resource Usage
```bash
# Run from the host where cAdvisor is running
docker stats cadvisor
# Raspberry Pi: Should be ~30-50MB RAM with optimizations
# Windows: ~100-200MB with full metrics
```

## Metrics Exported

### Container Metrics (Enabled)
- `container_cpu_usage_seconds_total` - CPU usage per container
- `container_memory_usage_bytes` - Memory usage
- `container_memory_working_set_bytes` - Active memory
- `container_spec_memory_limit_bytes` - Memory limits
- `container_cpu_cfs_throttled_seconds_total` - CPU throttling

### Disabled Metrics (For Reference)
These are disabled but can be re-enabled if needed:
- Network I/O per interface
- Disk read/write operations
- Per-CPU core statistics
- TCP/UDP connection counts
- Process-level metrics

## Integration Points

### Prometheus Scraping
Prometheus scrapes cAdvisor from both hosts:
```yaml
# In prometheus.yml
- job_name: 'cadvisor-pi'
  static_configs:
    - targets: ['192.168.50.216:8080']
      labels:
        instance: 'raspberry-pi'
        host: 'pi3'
  scrape_interval: 30s  # Match Pi housekeeping_interval

- job_name: 'cadvisor-windows'
  static_configs:
    - targets: ['192.168.50.40:8081']
      labels:
        instance: 'windows-server'
        host: 'ben-server'
  scrape_interval: 15s  # Match Windows housekeeping_interval
```

### Homepage Dashboard
Add to services.yaml:
```yaml
- Pi System Monitor:
    icon: cadvisor.png
    href: http://192.168.50.216:8080
    description: Container metrics
    widget:
      type: cadvisor
      url: http://192.168.50.216:8080
```

### Grafana Dashboards
Recommended dashboards:
- **893**: Docker container metrics
- **10619**: Docker monitoring (cAdvisor)
- **11600**: Docker & system monitoring

## Troubleshooting

### High Memory Usage
1. Check storage_duration: Should be 2m0s
2. Verify disabled_metrics includes disk,network,process
3. Increase housekeeping_interval to 60s if needed
4. Check container count: `docker ps --no-trunc | wc -l`

### Missing Metrics
1. Verify privileged mode is enabled
2. Check all required volumes are mounted
3. Test endpoint: `curl http://192.168.50.216:8080/metrics`
4. Review logs for volume mount errors

### Container Fails to Start
1. Check Docker socket access: `ls -l /var/run/docker.sock`
2. Verify paths exist: `/sys`, `/var/lib/docker`, etc.
3. Check for port 8080 conflicts: `ss -tulnp | grep 8080`
4. Review startup logs: `docker logs cadvisor`

### Prometheus Not Scraping
1. Test connectivity from Windows: `curl http://192.168.50.216:8080/metrics`
2. Check Prometheus targets: http://localhost:9090/targets
3. Verify scrape_interval matches or exceeds housekeeping_interval
4. Review Prometheus logs for errors

## Best Practices

1. **Keep Metrics Minimal**: Only enable metrics you actively use
2. **Monitor Resource Usage**: `docker stats cadvisor` periodically
3. **Match Scrape Intervals**: Prometheus scrape ≥ housekeeping_interval
4. **Don't Over-Optimize**: 30s housekeeping is good balance for Pi 3
5. **Regular Updates**: Watchtower keeps cAdvisor updated

## Performance Tuning

### If RAM Usage Too High
```bash
--storage_duration=1m0s  # Reduce to 1 minute
--housekeeping_interval=60s  # Increase interval
--disable_metrics=disk,diskIO,network,tcp,udp,percpu,sched,process,hugetlb
```

### If CPU Usage Too High
```bash
--max_housekeeping_interval=120s  # Extend to 2 minutes
--housekeeping_interval=60s
```

### For More Detailed Metrics (if RAM allows)
```bash
# Remove some disabled metrics
--disable_metrics=percpu,sched,process  # Keep network and disk
```

## Security Considerations

- **Privileged Mode**: Required but grants full host access
- **Read-Only Mounts**: All volumes except /var/run are read-only
- **No Authentication**: cAdvisor web UI is unauthenticated
- **Network Isolation**: Should only be accessible from local network
- **Nginx Proxy**: Don't expose externally without authentication

## Raspberry Pi 3 Specific Notes

### Expected Resource Usage
- **RAM**: 30-50MB (with optimizations)
- **CPU**: <5% average, spikes during housekeeping
- **Disk I/O**: Minimal (read-only operations)

### ARM Architecture
- Use `gcr.io/cadvisor/cadvisor:latest` (supports ARM64)
- Some metrics may behave differently on ARM vs x86
- Temperature monitoring works differently (use node-exporter)

### Limitations on Pi 3
- Cannot monitor hardware temperature (use node-exporter instead)
- Some advanced CPU metrics unavailable on ARM
- Disk metrics less detailed than on x86 systems

## Comparison with Windows cAdvisor

| Feature | Windows Host | Raspberry Pi |
|---------|--------------|--------------|
| Metrics | Full set | Optimized subset |
| Housekeeping | 10s | 30s |
| Storage Duration | 5m | 2m |
| RAM Usage | 100-200MB | 30-50MB |
| Disabled Metrics | None | disk,network,process,etc. |

## Advanced Configuration

### Enable Specific Metrics
```bash
# Remove from disable_metrics to re-enable:
--disable_metrics=percpu,sched,process  # Enable network and disk
```

### Custom Housekeeping
```bash
--housekeeping_interval=45s  # Custom interval
--max_housekeeping_interval=90s
```

### Prometheus Histograms
```bash
--enable_load_reader=true  # Add CPU load metrics
--application_metrics_count_limit=100  # Limit metric cardinality
```

## Monitoring cAdvisor Itself

### Prometheus Queries
```promql
# cAdvisor memory usage
container_memory_usage_bytes{name="cadvisor"}

# cAdvisor CPU usage
rate(container_cpu_usage_seconds_total{name="cadvisor"}[5m])

# Metric collection lag
cadvisor_version_info
```

### Health Check
```bash
# Test endpoint
curl -s http://192.168.50.216:8080/healthz
# Should return 200 OK

# Check metrics endpoint
curl -s http://192.168.50.216:8080/metrics | head -n 20
```

## When to Adjust Configuration

### Add More Metrics
If you need disk or network metrics:
```bash
--disable_metrics=percpu,sched,process  # Remove disk,network from list
```

### Reduce Resource Usage Further
If still using too much RAM:
```bash
--storage_duration=30s  # Minimum recommended
--housekeeping_interval=120s  # Very long interval
--disable_metrics=disk,diskIO,network,tcp,udp,percpu,sched,process,hugetlb,referenced_memory
```

### Increase Metric Frequency
If 30s is too slow for your monitoring:
```bash
--housekeeping_interval=15s  # Faster but more CPU
--storage_duration=3m0s  # Keep more history
```
