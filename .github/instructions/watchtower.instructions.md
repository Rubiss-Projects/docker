---
applyTo: "{pi/watchtower/**,watchtower/**}"
---

# Watchtower Expert Instructions

You are an expert in Watchtower automated Docker container updates for both Raspberry Pi and Windows hosts.

## Service Overview
Watchtower automatically monitors Docker containers for new image versions and updates them. It pulls the latest image, stops the old container, and starts a new one with the same configuration. This service runs on both the Raspberry Pi and Windows host with similar configurations.

## Technical Configuration

### Docker Compose Patterns
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock  # Required for Docker API access
environment:
  - TZ=America/New_York
  - WATCHTOWER_SCHEDULE=0 0 4 * * *  # 4 AM daily (cron format)
  - WATCHTOWER_CLEANUP=true  # Remove old images
  - WATCHTOWER_INCLUDE_STOPPED=true  # Update stopped containers
  - WATCHTOWER_POLL_INTERVAL=86400  # 24 hours (fallback)
restart: unless-stopped
```

### Critical Requirements
- **MUST** mount Docker socket: `/var/run/docker.sock`
- Requires access to Docker daemon
- No network ports needed (doesn't expose anything)

## Configuration Options

### Scheduling
```bash
# Cron format: second minute hour day month weekday
WATCHTOWER_SCHEDULE=0 0 4 * * *  # 4 AM daily
WATCHTOWER_SCHEDULE=0 0 */6 * * *  # Every 6 hours
WATCHTOWER_SCHEDULE=0 30 3 * * 0  # 3:30 AM Sundays only
```

### Update Behavior
```yaml
WATCHTOWER_CLEANUP=true  # Remove old images after update (recommended)
WATCHTOWER_INCLUDE_STOPPED=true  # Update even stopped containers
WATCHTOWER_INCLUDE_RESTARTING=true  # Include restarting containers
WATCHTOWER_REVIVE_STOPPED=false  # Don't start stopped containers
WATCHTOWER_ROLLING_RESTART=false  # Update all at once (default)
```

### Filtering
```yaml
# Update only specific containers
WATCHTOWER_MONITOR_ONLY=true  # Check but don't update (notifications only)
# Or use labels on other containers:
labels:
  - com.centurylinklabs.watchtower.enable=true  # Explicitly enable
  - com.centurylinklabs.watchtower.enable=false  # Explicitly disable
```

### Notifications
```yaml
WATCHTOWER_NOTIFICATIONS=slack  # Options: slack, email, msteams, gotify, shoutrrr
WATCHTOWER_NOTIFICATION_URL=https://hooks.slack.com/...
WATCHTOWER_NOTIFICATION_REPORT=true  # Send report even if no updates
```

## Common Tasks

### Viewing Logs
```bash
docker logs watchtower -f
```

### Force Update Check
```bash
docker exec watchtower /watchtower --run-once
```

### Check What Would Be Updated (Dry Run)
```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower --run-once --dry-run
```

### Update Single Container
```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower --run-once container_name
```

## Container Labels for Control

### Disable Watchtower for Specific Container
```yaml
# In the target container's docker-compose.yml
labels:
  - com.centurylinklabs.watchtower.enable=false
```

### Custom Update Schedule
```yaml
labels:
  - com.centurylinklabs.watchtower.enable=true
  - com.centurylinklabs.watchtower.schedule=0 0 2 * * *  # Override default
```

### Stop Signal and Timeout
```yaml
labels:
  - com.centurylinklabs.watchtower.stop-signal=SIGTERM
  - com.centurylinklabs.watchtower.stop-timeout=30s
```

## Integration Points

### Homepage Dashboard
Watchtower typically doesn't need homepage integration (no web UI). Consider adding a status indicator:
- Use Docker container health check
- Link to logs if needed

### Monitoring
- Check logs for update activity
- Monitor Docker events for container recreation
- Use Prometheus exporters for Docker events

## Troubleshooting

### Containers Not Updating
1. Check Watchtower logs: `docker logs watchtower`
2. Verify Docker socket is mounted correctly
3. Check container labels (watchtower.enable)
4. Verify cron schedule format
5. Test with `--run-once` flag

### Update Failures
1. Check image registry is accessible
2. Verify sufficient disk space for new images
3. Review container logs after update
4. Check for breaking changes in new image version
5. Ensure WATCHTOWER_CLEANUP removes old images

### Permission Errors
1. Ensure Watchtower can access Docker socket
2. Check Docker socket permissions: `ls -l /var/run/docker.sock`
3. Verify Watchtower is running on same Docker host

### Containers Fail After Update
1. Review breaking changes in image changelog
2. Check container logs: `docker logs container_name`
3. Rollback: `docker pull image:old_tag && docker-compose up -d`
4. Consider disabling auto-updates for problematic containers

## Best Practices

1. **Test Schedule**: Start with weekly updates, adjust as needed
2. **Cleanup Old Images**: Enable `WATCHTOWER_CLEANUP=true`
3. **Monitor Logs**: Regularly check for update activity and errors
4. **Selective Updates**: Disable for production/critical containers
5. **Backup First**: Ensure backups before auto-updates
6. **Pin Versions**: Use specific tags for critical services instead of `latest`
7. **Notification Setup**: Configure alerts for update failures
8. **Off-Hours Updates**: Schedule during low-traffic periods (4 AM)

## Security Considerations

- **Docker Socket Access**: Watchtower has full Docker control
- **Trust Images**: Only auto-update trusted image sources
- **Network Isolation**: Watchtower doesn't need network access (only Docker socket)
- **Read-Only Root**: Consider running with `--read-only` flag
- **Least Privilege**: Consider using Docker socket proxy (e.g., Tecnativa's docker-socket-proxy)

## Advanced Configuration

### Update Only Specific Labels
```yaml
WATCHTOWER_LABEL_ENABLE=true  # Only update containers with enable=true label
```

### Notification Example (Slack)
```yaml
WATCHTOWER_NOTIFICATIONS=slack
WATCHTOWER_NOTIFICATION_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
WATCHTOWER_NOTIFICATION_REPORT=true
```

### HTTP API Mode
```yaml
WATCHTOWER_HTTP_API_UPDATE=true
WATCHTOWER_HTTP_API_TOKEN=your_secret_token
WATCHTOWER_HTTP_API_PORT=8080
# Trigger via: curl -H "Authorization: Bearer your_secret_token" http://localhost:8080/v1/update
```

### Custom Commands Before/After Update
Use Docker labels:
```yaml
labels:
  - com.centurylinklabs.watchtower.lifecycle.pre-update=/backup.sh
  - com.centurylinklabs.watchtower.lifecycle.post-update=/notify.sh
```

## Raspberry Pi 3 Optimization

- Watchtower is extremely lightweight (~10MB RAM)
- Image pulls can be slow on Pi 3 (ARM architecture)
- Consider larger `stop_grace_period` for slower hardware
- Monitor disk space (old images accumulate if cleanup disabled)
- Updates at 4 AM minimize impact during low activity

## Watchtower Command Reference

### Run Once
```bash
docker exec watchtower /watchtower --run-once
```

### Dry Run
```bash
docker exec watchtower /watchtower --run-once --dry-run
```

### Update Specific Container
```bash
docker exec watchtower /watchtower --run-once container_name
```

### Debug Mode
```bash
docker exec watchtower /watchtower --run-once --debug
```

## Integration with CI/CD

Watchtower complements CI/CD by:
- Automatically pulling images built by CI
- No manual deployment needed for dev/staging
- Pair with image tags (e.g., `app:staging` auto-updates staging)
- Production should use explicit version tags

## When NOT to Use Watchtower

- Production environments requiring change control
- Containers needing manual migration steps
- Services with frequent breaking changes
- Applications requiring zero-downtime deployments
- Containers with complex dependencies requiring orchestration
