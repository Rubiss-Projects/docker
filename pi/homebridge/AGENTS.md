# Homebridge Service Guidance

Use this guidance when working on Homebridge configuration and HomeKit integration.

## Service Overview
Homebridge enables HomeKit support for smart home devices that don't natively support it. This service bridges non-HomeKit devices to Apple's Home app.

## Technical Configuration

### Network Requirements
- **CRITICAL**: Must use `network_mode: host` for mDNS/Bonjour discovery
- Runs on port 8581 (web UI)
- HomeKit port 51826 must be accessible
- No port mapping needed due to host networking

### Docker Compose Patterns
```yaml
network_mode: host  # REQUIRED for HomeKit discovery
restart: unless-stopped
volumes:
  - ./config:/homebridge  # Persistent config and plugins
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/New_York
```

### Volume Structure
- `config/` - Contains `config.json`, `accessories/`, and installed plugins
- Config is mounted to `/homebridge` inside container
- Permissions must match PUID/PGID (1000:1000)

## Common Tasks

### Adding Plugins
```bash
docker exec homebridge npm install -g homebridge-plugin-name
docker restart homebridge
```

### Viewing Logs
```bash
docker logs homebridge -f
```

### Backup Configuration
```bash
tar -czf homebridge-backup-$(date +%Y%m%d).tar.gz config/
```

## Integration Points

### Homepage Dashboard
- Widget type: `homebridge`
- URL: `http://192.168.50.216:8581`
- Requires username/password from Homebridge config

### SWAG reverse proxy
- Proxy to: `192.168.50.216:8581`
- WebSocket support: Enabled
- SSL: Recommended for external access

## Troubleshooting

### Device Discovery Issues
1. Verify host networking is enabled
2. Check firewall allows mDNS (port 5353)
3. Ensure device and Pi are on same network
4. Restart Homebridge service

### Plugin Errors
- Check Node.js version compatibility
- View logs for specific error messages
- Some plugins require additional system packages
- Use `npm install -g --unsafe-perm` for permission issues

### HomeKit Pairing Problems
- Remove bridge from Home app and re-pair
- Check HomeKit code in Homebridge UI
- Ensure only one bridge per Homebridge instance
- Reset Homebridge cached accessories if needed

## Best Practices

1. **Regular Backups**: Config contains all plugins and settings
2. **Update Plugins Carefully**: Test updates before deploying
3. **Monitor Logs**: Watch for plugin errors or deprecation warnings
4. **Use Child Bridges**: Isolate problematic plugins
5. **Resource Monitoring**: Track CPU/RAM usage for plugin performance

## Security Considerations

- Change default admin password immediately
- Use strong HomeKit setup code
- Enable HTTPS for remote access
- Limit external exposure via firewall rules
- Keep plugins updated for security patches

## Raspberry Pi 3 Optimization

- Limit number of plugins (1GB RAM constraint)
- Disable unnecessary features in plugins
- Use lightweight plugins where possible
- Monitor temperature and CPU usage
- Consider disabling video streaming plugins
