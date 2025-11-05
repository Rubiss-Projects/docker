---
applyTo: "pi/pi-hole/**"
---

# Pi-hole Service Expert Instructions

You are an expert in Pi-hole DNS ad blocking and network-wide filtering.

## Service Overview
Pi-hole acts as a DNS sinkhole, blocking ads and trackers at the network level for all devices. It provides DNS resolution with built-in blocklists.

## Technical Configuration

### Network Requirements
- DNS: Port 53 (TCP/UDP)
- DHCP: Port 67 (UDP) - Optional
- Web Interface: Port 80 (HTTP)
- Static IP: 192.168.50.41 (configured via DHCP reservation)

### Docker Compose Patterns
```yaml
ports:
  - "53:53/tcp"
  - "53:53/udp"
  - "67:67/udp"  # DHCP (optional)
  - "80:80/tcp"  # Web UI
volumes:
  - ./etc-pihole:/etc/pihole
  - ./etc-dnsmasq.d:/etc/dnsmasq.d
environment:
  - TZ=America/New_York
  - WEBPASSWORD=${PIHOLE_PASSWORD}
  - FTLCONF_LOCAL_IPV4=192.168.50.41
  - PIHOLE_DNS_=1.1.1.1;1.0.0.1  # Cloudflare DNS
cap_add:
  - NET_ADMIN  # Required for DHCP
restart: unless-stopped
```

### Volume Structure
- `etc-pihole/` - Contains gravity database, custom lists, FTL config
- `etc-dnsmasq.d/` - Custom DNS configurations
- **IMPORTANT**: These directories are in `.gitignore` (contain user data)

## Environment Variables

### Required
- `TZ` - Timezone for logs and stats
- `WEBPASSWORD` - Admin interface password (stored in .env)
- `FTLCONF_LOCAL_IPV4` - Pi's static IP address

### Optional
- `PIHOLE_DNS_` - Upstream DNS servers (semicolon-separated)
- `DNSSEC` - Enable DNSSEC validation (true/false)
- `CONDITIONAL_FORWARDING` - Enable for local network name resolution
- `DNSMASQ_LISTENING` - `all`, `local`, or `single` (default: local)

## Common Tasks

### Updating Gravity (Blocklists)
```bash
docker exec pihole pihole -g
```

### Viewing Logs
```bash
docker logs pihole -f
docker exec pihole pihole -t  # Tail FTL log
```

### Backup Configuration
```bash
tar -czf pihole-backup-$(date +%Y%m%d).tar.gz etc-pihole/ etc-dnsmasq.d/
```

### Restore Configuration
```bash
tar -xzf pihole-backup-YYYYMMDD.tar.gz
docker restart pihole
```

### Get API Key
```bash
docker exec pihole cat /etc/pihole/setupVars.conf | grep WEBPASSWORD
```

## Integration Points

### Homepage Dashboard
- Widget type: `pihole`
- URL: `http://192.168.50.41:80`
- Requires API key from setupVars.conf
- Shows: queries, blocked, percent blocked, gravity entries

### Prometheus Monitoring
- Pi-hole Exporter can be added for metrics
- Alternative: Use built-in API for stats

### Network Configuration
Devices must point to Pi-hole for DNS:
1. **Router DHCP**: Set DNS to 192.168.50.41
2. **Manual**: Configure each device's DNS settings
3. **Test**: `nslookup doubleclick.net 192.168.50.41` should return 0.0.0.0

### Nginx Proxy Manager
- Proxy to: `192.168.50.41:80`
- Custom location: `/admin/` (Pi-hole web interface)
- SSL: Recommended for external access

## Troubleshooting

### DNS Not Resolving
1. Check Pi-hole container is running: `docker ps`
2. Verify port 53 is listening: `ss -tulnp | grep :53`
3. Test DNS: `nslookup google.com 192.168.50.41`
4. Check upstream DNS settings in web UI
5. Review FTL logs: `docker exec pihole pihole -t`

### Web Interface Not Loading
1. Check port 80 is exposed: `docker ps`
2. Verify lighttpd is running inside container
3. Check WEBPASSWORD is set in .env
4. Clear browser cache/try incognito

### High Memory Usage
1. Pi-hole with large blocklists can use 200-400MB RAM
2. Reduce blocklist count if needed
3. Adjust FTL cache settings via FTLCONF variables
4. Monitor with: `docker stats pihole`

### Blocklists Not Updating
1. Run gravity update manually: `docker exec pihole pihole -g`
2. Check internet connectivity from container
3. Verify blocklist URLs are accessible
4. Check disk space: `df -h`

## Best Practices

1. **Blocklist Management**: Start with default lists, add carefully
2. **Whitelist Important Domains**: Some services break with aggressive blocking
3. **Regular Updates**: Update gravity weekly (automatic in Pi-hole)
4. **Monitor Query Log**: Identify false positives
5. **Backup Regularly**: Before major changes or updates
6. **Use Groups**: Organize clients and blocklists via web UI

## Security Considerations

- Change default admin password immediately
- Use strong password stored in .env file
- Limit web interface to local network only
- Enable DNSSEC for DNS validation
- Use encrypted upstream DNS (DNS-over-HTTPS) if desired
- Don't expose port 53 to internet (DNS amplification attacks)

## Advanced Configuration

### Custom DNS Records
Add to `etc-dnsmasq.d/02-custom.conf`:
```conf
address=/local.domain.com/192.168.1.100
```

### Local DNS Records
Add to `etc-pihole/custom.list`:
```
192.168.50.40 homeassistant.local
192.168.50.41 pihole.local
```

### Conditional Forwarding
Enable in web UI for local network hostname resolution:
- Local network: 192.168.50.0/24
- Router IP: 192.168.50.1
- Local domain: lan (or your router's domain)

## Raspberry Pi 3 Optimization

- Pi-hole is lightweight and well-suited for Pi 3
- Typical RAM usage: 150-300MB with default blocklists
- CPU usage is minimal except during gravity updates
- Use SSD/USB drive for faster database operations (optional)
- Monitor temperature during initial gravity update

## API Reference

### Get Statistics
```bash
curl http://192.168.50.41/admin/api.php
```

### Get Query Count
```bash
curl http://192.168.50.41/admin/api.php?summaryRaw
```

### Enable/Disable Blocking
```bash
# Disable for 10 seconds
docker exec pihole pihole disable 10s
# Enable
docker exec pihole pihole enable
```
