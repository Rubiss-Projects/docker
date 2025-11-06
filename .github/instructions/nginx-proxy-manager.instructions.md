---
applyTo: "nginx-proxy-manager/**"
---

# Nginx Proxy Manager Expert Instructions

You are an expert in Nginx Proxy Manager for reverse proxy, SSL termination, and domain management.

## Service Overview
Nginx Proxy Manager provides a web UI for managing Nginx reverse proxy configurations. It handles SSL certificates via Let's Encrypt, proxies requests to internal services, and manages custom domains.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "80:80"   # HTTP
  - "443:443" # HTTPS
  - "81:81"   # Admin UI
volumes:
  - ./data:/data
  - ./letsencrypt:/etc/letsencrypt
networks:
  - proxynet
restart: unless-stopped
```

### Critical Files
- `data/database.sqlite` - NPM configuration database
- `letsencrypt/` - SSL certificates from Let's Encrypt
- `data/nginx/` - Custom Nginx configurations

### Default Credentials
- Email: `admin@example.com`
- Password: `changeme`
- **MUST CHANGE** on first login

## Common Tasks

### Access Admin UI
- URL: `http://localhost:81` or `http://server-ip:81`
- Change password immediately after first login

### Create Proxy Host
1. Go to Hosts > Proxy Hosts
2. Click "Add Proxy Host"
3. Configure:
   - Domain Names: `service.benlawson.dev`
   - Scheme: `http` (internal services are usually HTTP)
   - Forward Hostname/IP: Container name (e.g., `plex`) or IP (e.g., `192.168.50.216`)
   - Forward Port: Service port (e.g., `32400` for Plex, `8581` for Homebridge)
   - Websockets Support: Enable if needed
4. Go to SSL tab:
   - Request New Certificate
   - Use Let's Encrypt
   - Email: Your email
   - Force SSL: Enable
   - HTTP/2: Enable
5. Save

### Renew SSL Certificates
- Automatic renewal via Let's Encrypt (NPM handles this)
- Manual renewal: SSL Certificates > Click certificate > Renew

### Backup Configuration
```powershell
# Stop NPM
docker compose stop

# Backup data and certificates
tar -czf npm-backup-$(Get-Date -Format "yyyyMMdd").tar.gz data/ letsencrypt/

# Start NPM
docker compose start
```

### View Logs
```powershell
docker logs nginx-proxy-manager -f
```

## Proxy Host Patterns

### Docker Service (Same Host)
```
Domain: service.benlawson.dev
Scheme: http
Forward Host: container_name
Forward Port: internal_port
Websockets: Enable if needed
SSL: Let's Encrypt (force SSL, HTTP/2)
```

Example for Plex:
- Domain: `plex.benlawson.dev`
- Forward to: `http://plex:32400`

### Remote Service (Raspberry Pi)
```
Domain: pihole.benlawson.dev
Scheme: http
Forward Host: 192.168.50.216
Forward Port: 80
SSL: Let's Encrypt
```

### Service Requiring WebSockets
Services like Grafana, Homepage, Bitwarden require WebSockets:
```
Websockets Support: ✓ Enable
```

### Service with Custom Path
For services not at root path:
```
Forward Host: service_name
Forward Port: port
Custom Locations:
  Location: /custom-path
  Forward to: http://service:port/custom-path
```

## Integration Points

### Homepage Dashboard
```yaml
- Nginx Proxy Manager:
    icon: nginx-proxy-manager.png
    href: http://localhost:81
    description: Reverse proxy management
```

### Docker Services
All services on `proxynet` network can be proxied by NPM using container names.

### DNS Configuration
Point domains to your public IP:
```
A Record: *.benlawson.dev → Your-Public-IP
```

Or individual subdomains:
```
A Record: plex.benlawson.dev → Your-Public-IP
A Record: grafana.benlawson.dev → Your-Public-IP
```

### Cloudflare Integration
If using Cloudflare DNS:
1. Set DNS records to Proxied (orange cloud)
2. Use Cloudflare SSL mode: Full (Strict)
3. NPM handles Let's Encrypt certificates
4. Cloudflare provides additional DDoS protection

## SSL Certificate Management

### Let's Encrypt Certificates
- Free, automated, 90-day validity
- NPM auto-renews at 30 days before expiration
- Supports wildcard certificates (*.benlawson.dev)

### Wildcard Certificate
1. SSL Certificates > Add SSL Certificate
2. Domain: `*.benlawson.dev`, `benlawson.dev`
3. Use DNS Challenge (required for wildcard)
4. DNS Provider: Select your provider (Cloudflare, etc.)
5. Enter API credentials
6. Save

### Custom Certificate
For self-signed or purchased certificates:
1. SSL Certificates > Add SSL Certificate
2. Select "Custom"
3. Upload certificate, key, and intermediate cert
4. Save

## Advanced Configuration

### Custom Nginx Configuration
For each proxy host, go to Advanced tab:
```nginx
# Example: Increase client max body size
client_max_body_size 100M;

# Example: Add custom headers
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Real-IP $remote_addr;

# Example: Disable buffering (for live streams)
proxy_buffering off;
```

### Access Lists (IP Whitelist/Blacklist)
1. Access Lists > Add Access List
2. Name: "Office Only"
3. Satisfy Any: At least one condition
4. Authorization:
   - Allow: `192.168.1.0/24`
   - Allow: `10.0.0.0/8`
   - Deny: `0.0.0.0/0` (deny all others)
5. Apply to proxy host in Access tab

### HTTP Authentication
1. Access Lists > Add Access List
2. Enable HTTP Basic Authentication
3. Add users with usernames/passwords
4. Apply to proxy host

## Troubleshooting

### Port 80/443 Already in Use
1. Check for existing web servers: `netstat -ano | findstr :80`
2. Stop conflicting services (IIS, Apache, etc.)
3. Ensure no other Docker containers bind to 80/443

### Cannot Access Admin UI (Port 81)
1. Check container is running: `docker ps`
2. Verify port is exposed: `docker port nginx-proxy-manager`
3. Test: `curl http://localhost:81`
4. Check firewall: `netsh advfirewall firewall show rule name=all`

### SSL Certificate Fails
1. Verify DNS points to your IP: `nslookup service.benlawson.dev`
2. Check port 80 is accessible from internet (Let's Encrypt validation)
3. Review NPM logs: `docker logs nginx-proxy-manager`
4. Try HTTP challenge instead of DNS challenge
5. Check Let's Encrypt rate limits (50 certs per domain per week)

### 502 Bad Gateway
1. Verify target service is running: `docker ps`
2. Check forward host/port is correct
3. Test connectivity: `docker exec nginx-proxy-manager curl http://service:port`
4. Ensure both NPM and target are on same network (proxynet)
5. Check target service logs

### WebSockets Not Working
1. Enable "Websockets Support" in proxy host
2. Check for custom Nginx config blocking WebSockets
3. Verify browser DevTools shows WebSocket connection

### 504 Gateway Timeout
1. Increase timeout in Advanced config:
```nginx
proxy_connect_timeout 600;
proxy_send_timeout 600;
proxy_read_timeout 600;
send_timeout 600;
```
2. Check target service is responding
3. Review target service logs for slow queries/operations

## Best Practices

1. **Change Default Credentials**: Immediately after first login
2. **Use Strong Passwords**: For admin and HTTP auth
3. **Enable Force SSL**: Redirect HTTP to HTTPS
4. **Enable HTTP/2**: Better performance
5. **Backup Regularly**: Database and certificates
6. **Monitor Certificate Expiry**: Check SSL tab regularly
7. **Use Access Lists**: Restrict sensitive services to trusted IPs
8. **Test Changes**: Verify each proxy host works before moving to next
9. **Use Container Names**: For Docker services (not IPs)
10. **Document Configurations**: Keep notes on custom Nginx configs

## Security Considerations

- **Admin UI Exposure**: Limit access to port 81 (firewall or VPN)
- **SSL Only**: Force HTTPS for all services
- **Access Control**: Use IP whitelisting for sensitive services
- **Strong Passwords**: For both NPM admin and HTTP auth
- **Regular Updates**: Keep NPM updated via Watchtower
- **Fail2Ban**: Consider adding for brute-force protection
- **Audit Logs**: Review access logs regularly
- **Cloudflare**: Additional layer of protection if using CF proxy

## Common Proxy Configurations

### Plex Media Server
```
Domain: plex.benlawson.dev
Forward: http://plex:32400
Websockets: No
SSL: Let's Encrypt, Force SSL
Custom Config:
  # Allow large uploads
  client_max_body_size 0;
  # Plex headers
  proxy_set_header X-Plex-Client-Identifier $http_x_plex_client_identifier;
  proxy_set_header X-Plex-Device $http_x_plex_device;
  proxy_set_header X-Plex-Device-Name $http_x_plex_device_name;
  proxy_set_header X-Plex-Platform $http_x_plex_platform;
```

### Grafana
```
Domain: grafana.benlawson.dev
Forward: http://grafana:3000
Websockets: Yes (for live updates)
SSL: Let's Encrypt, Force SSL
```

### Homebridge (Pi)
```
Domain: homebridge.benlawson.dev
Forward: http://192.168.50.216:8581
Websockets: Yes
SSL: Let's Encrypt, Force SSL
```

### Pi-hole (Pi)
```
Domain: pihole.benlawson.dev
Forward: http://192.168.50.216:80
Websockets: No
SSL: Let's Encrypt, Force SSL
Custom Locations:
  Location: /admin
  Forward: http://192.168.50.216:80/admin
```

### Bitwarden
```
Domain: bitwarden.benlawson.dev
Forward: http://bitwarden:80
Websockets: Yes (for real-time sync)
SSL: Let's Encrypt, Force SSL
Custom Config:
  client_max_body_size 128M;
```

## Monitoring and Maintenance

### Check Certificate Expiry
1. SSL Certificates tab
2. Look at "Expires" column
3. Should auto-renew 30 days before expiry

### Review Access Logs
```powershell
# NPM access logs
docker exec nginx-proxy-manager cat /data/logs/proxy-host-*.log

# Nginx error logs
docker exec nginx-proxy-manager cat /data/logs/error.log
```

### Database Backup
```powershell
# Manual database export
docker exec nginx-proxy-manager sqlite3 /data/database.sqlite ".backup '/data/database-backup.sqlite'"
```

### Update NPM
Handled automatically by Watchtower, or manually:
```powershell
cd E:\Docker\nginx-proxy-manager
docker compose pull
docker compose up -d
```

## API Usage (Advanced)

NPM has an API for automation:

### Login
```powershell
$auth = Invoke-RestMethod -Method Post -Uri "http://localhost:81/api/tokens" -Body (@{
    identity = "admin@example.com"
    secret = "your-password"
} | ConvertTo-Json) -ContentType "application/json"

$token = $auth.token
```

### List Proxy Hosts
```powershell
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Uri "http://localhost:81/api/nginx/proxy-hosts" -Headers $headers
```

### Create Proxy Host
```powershell
$body = @{
    domain_names = @("new.benlawson.dev")
    forward_scheme = "http"
    forward_host = "service"
    forward_port = 8080
    certificate_id = 1
    ssl_forced = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:81/api/nginx/proxy-hosts" -Headers $headers -Body $body -ContentType "application/json"
```

## Stream Configuration (Non-HTTP)

For TCP/UDP streams (not HTTP):
1. Streams tab > Add Stream
2. Configure:
   - Incoming Port: External port
   - Forward Host: Internal host
   - Forward Port: Internal port
3. Example: SSH tunnel, game servers

## Multi-Container Setup

NPM works seamlessly with multiple containers:
- All containers on `proxynet` network
- Use container names as forward hosts
- No IP addresses needed for Docker services
- NPM resolves container names via Docker DNS

## Disaster Recovery

### Full Restore
```powershell
# Stop NPM
docker compose stop

# Restore backup
tar -xzf npm-backup-YYYYMMDD.tar.gz

# Start NPM
docker compose start
```

### Migrate to New Server
1. Backup on old server: `tar -czf npm-backup.tar.gz data/ letsencrypt/`
2. Transfer to new server
3. Extract: `tar -xzf npm-backup.tar.gz`
4. Update DNS to point to new server IP
5. Start NPM: `docker compose up -d`
6. Certificates will auto-renew on new server

This centralized proxy architecture allows secure external access to all internal services with automated SSL management.
