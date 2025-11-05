---
applyTo: "cloudflare-duc-go/**"
---

# Cloudflare Dynamic DNS Updater Expert Instructions

You are an expert in Cloudflare Dynamic DNS (DDNS) configuration using cloudflare-ddns-updater.

## Service Overview
Cloudflare DDNS Updater automatically updates Cloudflare DNS A/AAAA records with your public IP address. Essential for homelab services with dynamic IPs, ensuring domains always point to current public IP.

## Technical Configuration

### Docker Compose Patterns
```yaml
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/Chicago
  - API_KEY=${CLOUDFLARE_API_KEY}
  - ZONE=${CLOUDFLARE_ZONE}
  - SUBDOMAIN=@  # Or specific subdomain
  - PROXIED=false
  - RRTYPE=A  # Or AAAA for IPv6
  - TTL=1  # Automatic TTL
  - CHECK_PERIOD=5m
volumes:
  - ./config:/config
restart: unless-stopped
```

### Environment Variables

#### Required
- `API_KEY` - Cloudflare API token (Zone:DNS:Edit permission)
- `ZONE` - Domain name (e.g., example.com)

#### Optional
- `SUBDOMAIN` - Subdomain to update (default: @ for root)
- `PROXIED` - Cloudflare proxy (true/false, default: false)
- `RRTYPE` - Record type (A or AAAA, default: A)
- `TTL` - DNS TTL in seconds (1 for automatic, default: 1)
- `CHECK_PERIOD` - IP check interval (default: 5m)

### No Ports Required
Background service, no exposed ports.

## Common Tasks

### First-Time Setup

**1. Get Cloudflare API Token**:
- Cloudflare Dashboard > My Profile > API Tokens
- Create Token > Custom Token
- Permissions:
  - Zone > DNS > Edit
- Zone Resources:
  - Include > Specific zone > example.com
- Continue, Create Token
- Copy token (shown once)

**2. Get Zone ID**:
- Cloudflare Dashboard > Select domain
- Right sidebar > Zone ID
- Copy Zone ID

**3. Configure Environment**:
```yaml
environment:
  - API_KEY=your_token_here
  - ZONE=example.com
  - SUBDOMAIN=home  # Creates home.example.com
```

**4. Start Container**:
```powershell
docker compose up -d
```

### Update Multiple Subdomains
Create multiple containers:
```yaml
services:
  ddns-root:
    image: oznu/cloudflare-ddns
    environment:
      - API_KEY=${CLOUDFLARE_API_KEY}
      - ZONE=example.com
      - SUBDOMAIN=@
  
  ddns-wildcard:
    image: oznu/cloudflare-ddns
    environment:
      - API_KEY=${CLOUDFLARE_API_KEY}
      - ZONE=example.com
      - SUBDOMAIN=*
```

### Enable Cloudflare Proxy
```yaml
- PROXIED=true
```

Benefits:
- Hides real IP address
- DDoS protection
- SSL/TLS encryption
- Caching

Limitations:
- HTTP/HTTPS traffic only
- Breaks non-HTTP services (SSH, game servers)

### Update IPv6 Address
```yaml
- RRTYPE=AAAA
```

### Check Update Status
```powershell
docker logs cloudflare-ddns
```

Expected output:
```
[INFO] Detected IP: 1.2.3.4
[INFO] DNS record updated: home.example.com -> 1.2.3.4
```

### Force Immediate Update
```powershell
docker compose restart cloudflare-ddns
```

## Integration Points

### Cloudflare Dashboard
View DNS records:
- Dashboard > Domain > DNS > Records
- See A/AAAA records updated automatically

### Nginx Proxy Manager
Point NPM proxy hosts to DDNS domains:
- Domain: home.example.com
- Forward: http://internal-service:port

### Dynamic IP Monitoring
Pair with notifications:
- Monitor logs for IP changes
- Alert on update failures

### Homepage Dashboard
```yaml
- Cloudflare DDNS:
    icon: cloudflare.png
    description: Dynamic DNS updater
```

(No direct widget available)

## Troubleshooting

### Updates Not Working
1. Check logs: `docker logs cloudflare-ddns`
2. Verify API token permissions
3. Ensure Zone ID is correct
4. Check domain exists in Cloudflare
5. Verify internet connectivity

### Authentication Errors
```
[ERROR] Authentication failed
```

**Fix**:
1. Verify API_KEY is correct
2. Check token permissions include Zone:DNS:Edit
3. Ensure token is for correct zone
4. Token may be expired, create new one

### Wrong IP Detected
```
[INFO] Detected IP: 192.168.1.1
```

**Cause**: Detecting internal IP instead of public
**Fix**: Container should auto-detect public IP via external services

### DNS Record Not Found
```
[ERROR] DNS record not found
```

**Fix**: Manually create initial DNS record in Cloudflare dashboard:
- Type: A
- Name: @ or subdomain
- Content: 0.0.0.0 (will be updated)
- Proxy: Off (or match PROXIED setting)
- TTL: Auto

### Too Frequent Updates
```yaml
- CHECK_PERIOD=15m  # Check less often
```

Reduces API calls and logs.

## Best Practices

1. **API Token Scope**: Limit to specific zone, DNS:Edit only
2. **Proxy Settings**: Use PROXIED=true for web services only
3. **Check Period**: 5-15 minutes balances responsiveness and API usage
4. **Multiple Subdomains**: Separate containers for different update requirements
5. **Logging**: Monitor logs for IP changes and failures
6. **Backup Token**: Store API token securely

## Security Considerations

- **API Token**: Protect token (full DNS control)
- **Token Permissions**: Minimum required (Zone:DNS:Edit)
- **Token Rotation**: Rotate periodically
- **Secrets Management**: Use .env file, don't commit to git
- **Proxy for Web**: Use Cloudflare proxy for HTTP/S services

## Advanced Configuration

### Update Multiple Zones
```yaml
services:
  ddns-zone1:
    environment:
      - ZONE=example.com
  
  ddns-zone2:
    environment:
      - ZONE=other-domain.net
```

### Wildcard Subdomain
```yaml
- SUBDOMAIN=*
```

Updates *.example.com wildcard record.

### Custom TTL
```yaml
- TTL=300  # 5 minutes
```

Options: 1 (auto), 120-86400 seconds

### Detect IP from Interface
Some images support:
```yaml
- INTERFACE=eth0
```

Uses IP from specific network interface.

### Webhook Notifications
No built-in webhook support. Use log monitoring:
```bash
docker logs -f cloudflare-ddns | grep -E 'ERROR|updated'
```

Or wrapper script to send notifications.

## API Token Creation Details

**Minimal Permissions**:
- Zone > DNS > Edit

**Zone Resources**:
- Include > Specific zone > example.com

**Client IP Filtering** (optional):
- Restrict to server IP for added security

**TTL**:
- Set token expiration if desired

## Common Use Cases

### Home Server with Dynamic IP
```yaml
- ZONE=home-server.com
- SUBDOMAIN=@
- PROXIED=false
- CHECK_PERIOD=5m
```

Keeps domain pointing to home IP for VPN, SSH, etc.

### Web Services Behind Cloudflare
```yaml
- ZONE=webapp.com
- SUBDOMAIN=app
- PROXIED=true
```

Web app benefits from Cloudflare CDN and protection.

### Multiple Services, One IP
```yaml
services:
  ddns-root:
    environment:
      - SUBDOMAIN=@
  ddns-vpn:
    environment:
      - SUBDOMAIN=vpn
  ddns-plex:
    environment:
      - SUBDOMAIN=plex
```

All point to same public IP, reverse proxy routes internally.

### IPv6 + IPv4 Dual Stack
```yaml
services:
  ddns-ipv4:
    environment:
      - RRTYPE=A
  ddns-ipv6:
    environment:
      - RRTYPE=AAAA
```

Updates both A and AAAA records.

## Monitoring

### Log Patterns
**Successful update**:
```
[INFO] Detected IP: 1.2.3.4
[INFO] DNS record updated: home.example.com -> 1.2.3.4
```

**No change**:
```
[INFO] Detected IP: 1.2.3.4
[INFO] DNS record already up to date
```

**Error**:
```
[ERROR] Failed to update DNS record: ...
```

### Health Check
No built-in health endpoint. Monitor via:
- Container status: `docker ps`
- Recent logs: `docker logs --tail 20 cloudflare-ddns`
- DNS lookup: `nslookup home.example.com`

### Alert on Failures
Use log monitoring tool (e.g., Loki, Promtail) to alert on ERROR log lines.

## Alternatives

### Cloudflare API Script
Custom PowerShell script:
```powershell
$zone = "example.com"
$record = "home"
$token = "your_token"

$ip = (Invoke-RestMethod -Uri "https://api.ipify.org").Trim()

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

# Get zone ID
$zoneResp = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones?name=$zone" -Headers $headers
$zoneId = $zoneResp.result[0].id

# Get DNS record ID
$recordResp = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/dns_records?name=$record.$zone" -Headers $headers
$recordId = $recordResp.result[0].id

# Update DNS record
$body = @{
    type = "A"
    name = $record
    content = $ip
    ttl = 1
    proxied = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/dns_records/$recordId" -Method Put -Headers $headers -Body $body
```

Schedule with Task Scheduler.

### Router-Based DDNS
Some routers support Cloudflare DDNS natively. Check router firmware.

## Cloudflare API Limits

**Free Plan**:
- 1,200 requests per 5 minutes
- DNS updates are very lightweight

**Rate Limit Handling**:
Container respects rate limits automatically. With 5-minute check period, well under limits.

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| API_KEY | (required) | Cloudflare API token |
| ZONE | (required) | Domain name |
| SUBDOMAIN | @ | Subdomain (@ for root, * for wildcard) |
| PROXIED | false | Enable Cloudflare proxy |
| RRTYPE | A | Record type (A or AAAA) |
| TTL | 1 | DNS TTL (1=auto, 120-86400) |
| CHECK_PERIOD | 5m | IP check interval |
| PUID | 1000 | User ID for file permissions |
| PGID | 1000 | Group ID for file permissions |
| TZ | UTC | Timezone |

This lightweight DDNS updater ensures homelab services remain accessible via Cloudflare DNS even with dynamic public IP addresses, integrating seamlessly with Cloudflare's CDN and security features.
