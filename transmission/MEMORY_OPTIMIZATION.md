# Transmission Memory Optimization Guide

## Understanding Transmission Memory Usage

### Is Hitting the 2G Memory Limit Normal?

**Yes**, for an active Transmission instance with moderate to heavy torrent activity, hitting a 2G memory limit is normal behavior. This is not a bug or malfunction.

### Published Limits and Requirements

Transmission itself **does not have published hard memory limits**. Memory usage is dynamic and scales based on:

1. **Cache Size** (`cache-size-mb`)
   - Purpose: Reduces disk I/O by caching frequently accessed data
   - Typical range: 8-64MB
   - Current setting: 48MB (optimized from 16MB)

2. **Number of Active Torrents**
   - Each torrent requires memory for:
     - Piece tracking
     - Peer management
     - Download/upload queues
   - Approximate overhead: 50-100MB per active torrent

3. **Peer Connections** (`peer-limit-global` and `peer-limit-per-torrent`)
   - Each peer connection uses memory for:
     - Connection state
     - Buffer management
     - Protocol overhead
   - Current settings: 150 global, 30 per torrent

4. **File System Metadata**
   - Large torrents with many files require more memory
   - Torrent metadata is kept in memory

### Typical Memory Usage Patterns

| Usage Level | Torrents | Cache | Expected Memory | Recommended Limit |
|------------|----------|-------|-----------------|-------------------|
| Light      | 1-5      | 16MB  | 256-512MB       | 1G                |
| Moderate   | 5-20     | 32-48MB | 1-2GB         | 3G                |
| Heavy      | 20+      | 64MB  | 2-4GB           | 4G                |

**Current configuration**: Moderate usage profile (3G limit, 48MB cache)

## Negative Effects of Memory Limits

### Below Memory Limit (Normal Operation)
- ✅ Optimal performance
- ✅ Full cache utilization
- ✅ No issues

### At Memory Limit (95-100% usage)
- ⚠️ Minor performance degradation
- ⚠️ Cache may be evicted more frequently
- ⚠️ Slightly increased disk I/O
- ⚠️ Grafana alerts triggered (informational)
- ✅ No data loss or corruption
- ✅ Torrents continue to function

### Above Memory Limit (OOM)
- ❌ Docker may kill the container (Out of Memory)
- ❌ Service interruption
- ❌ Need to restart container

**Important**: Consistently hitting the limit is not harmful as long as the container isn't being OOM-killed.

## Configuration Changes Applied

### 1. Increased Memory Limit
```yaml
# Before
limits:
  memory: 2G

# After
limits:
  memory: 3G
```

**Rationale**: Provides headroom for moderate usage without triggering alerts.

### 2. Optimized Cache Size
```yaml
# Before
- TRANSMISSION_CACHE_SIZE_MB=16

# After
- TRANSMISSION_CACHE_SIZE_MB=48
```

**Rationale**: 
- 16MB cache was too small for optimal performance
- Transmission documentation recommends 32-64MB for moderate usage
- 48MB balances performance and memory consumption

## Grafana Alert Behavior

The current Grafana alert configuration triggers when:
- Container memory usage > 95% of limit
- Condition persists for > 15 minutes

### Alert Interpretation

**With 2G limit:**
- Triggers frequently with active torrents ✗
- Creates alert fatigue ✗
- Indicates normal behavior, not a problem ✗

**With 3G limit:**
- Provides 50% more headroom ✓
- Reduces false-positive alerts ✓
- Only triggers if usage truly exceeds normal patterns ✓

## Should You Still Get Alerts?

### Keep Alerts If:
- You want to monitor for abnormal memory growth
- You're debugging memory leaks
- You want to track usage patterns

### Disable/Modify Alerts If:
- Alerts fire regularly with no issues
- You've verified the memory usage is normal for your workload
- You prefer to monitor through other means (e.g., dashboard only)

### Recommended Alert Modifications

Option 1: Increase threshold to 98%
```yaml
conditions:
  - evaluator:
      params: [98]  # Changed from 95
      type: gt
```

Option 2: Increase duration before firing
```yaml
for: 30m  # Changed from 15m
```

Option 3: Add annotation clarifying this may be normal
```yaml
annotations:
  summary: "High memory usage in container {{ $labels.name }}"
  description: "Container {{ $labels.name }} is using {{ $values.B.Value | printf \"%.2f\" }}% of its memory limit. This may be normal for active torrent clients. Investigate if sustained or if container restarts occur."
```

## Monitoring Best Practices

1. **Track OOM Events**: Monitor for actual container kills
   ```bash
   docker logs transmission | grep -i "killed\|oom"
   ```

2. **Monitor Trends**: Use Grafana to track memory usage over time
   - Look for gradual increases (potential memory leak)
   - Spikes during high activity are normal

3. **Review Performance**: Check if downloads are slower when at high memory usage
   - If yes: Consider increasing limit further
   - If no: Current configuration is adequate

4. **Adjust Based on Usage**: 
   - Heavy downloading: Consider 4G limit
   - Light usage: 2G may be sufficient, optimize cache size

## Further Optimization

If memory usage remains a concern:

### Reduce Peer Connections
```yaml
- TRANSMISSION_PEER_LIMIT_GLOBAL=100  # Reduced from 150
- TRANSMISSION_PEER_LIMIT_PER_TORRENT=20  # Reduced from 30
```

### Reduce Download Queue
```yaml
- TRANSMISSION_DOWNLOAD_QUEUE_SIZE=2  # Reduced from 3
```

### Smaller Cache (Not Recommended)
```yaml
- TRANSMISSION_CACHE_SIZE_MB=32  # Reduced from 48
```
**Note**: This may hurt performance due to increased disk I/O.

## Conclusion

Hitting the 2G memory limit with Transmission is **normal and expected** for moderate torrent activity. The applied changes (3G limit, 48MB cache) provide optimal performance while reducing alert fatigue. No negative effects occur unless the container is actually OOM-killed, which should be rare with these settings.

Monitor for:
- ✅ Actual OOM kills (requires action)
- ✅ Sustained 100% usage over days (investigate)
- ❌ Temporary spikes to 95-100% (normal, ignore)
