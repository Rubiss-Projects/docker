---
applyTo: swag/**
---

# SWAG Reverse Proxy Expert Instructions

You are an expert in SWAG (Secure Web Application Gateway) for reverse proxy, SSL termination, and domain management.

## Overview

SWAG is a LinuxServer.io container that bundles Nginx, Let's Encrypt SSL certificates, fail2ban, and other security features. It provides automatic SSL certificate generation/renewal and acts as the main reverse proxy for all external-facing services.

## Architecture

### Current Setup
- **Container**: `swag` (lscr.io/linuxserver/swag:latest)
- **Ports**: 443 (HTTPS), 80 (HTTP)
- **SSL Provider**: Let's Encrypt (Cloudflare DNS validation)
- **Domain**: *.benlawson.dev (wildcard certificate)
- **Networks**: 
  - `socket-proxy-net` - For Docker socket access via proxy
  - `proxynet` - For routing to backend services
- **Docker Mods**:
  - `swag-dashboard` - Analytics dashboard at https://dashboard.benlawson.dev
  - `swag-ondemand` - Automatic container start/stop on access
  - `swag-auto-uptime-kuma` - Automated Uptime Kuma monitor sync
  - `universal-docker` - Required for auto-uptime-kuma to access Docker socket

### Key Features
1. **Automatic SSL**: Wildcard certificate for *.benlawson.dev, auto-renewed
2. **Reverse Proxy**: Routes external HTTPS to internal Docker services
3. **Security**: fail2ban, ModSecurity, rate limiting
4. **Dashboard**: Real-time analytics via swag-dashboard mod
5. **On-Demand Containers**: Services auto-start when accessed (ollama, open-webui)
6. **Automated Monitoring**: Syncs container labels to Uptime Kuma monitors

## Configuration Files

### Primary Locations
```
/mnt/e/Docker/swag/config/nginx/
├── nginx.conf              # Main Nginx configuration
├── proxy-confs/            # Reverse proxy configurations
│   ├── *.subdomain.conf    # Active proxy configs
│   └── *.sample            # Sample configurations
├── ssl.conf                # SSL/TLS settings
├── site-confs/             # Additional site configs
│   └── default.conf        # Default server (returns 444 for undefined domains)
└── resolver.conf           # DNS resolver settings
```

### Environment Variables
Located in `/mnt/e/Docker/swag/.env`:
- `PUID`, `PGID`, `TZ` - User/group/timezone
- `URL=benlawson.dev` - Base domain
- `SUBDOMAINS=wildcard` - Request wildcard cert
- `VALIDATION=dns` - Use DNS validation
- `DNSPLUGIN=cloudflare` - Cloudflare for DNS challenges
- `EMAIL` - Let's Encrypt registration email
- `STAGING=false` - Use production certificates

### Uptime Kuma Sync Variables
- `UPTIME_KUMA_URL` - Internal URL (e.g., `http://uptime-kuma:3001/`)
- `UPTIME_KUMA_USER` - Admin username
- `UPTIME_KUMA_PASS` - Admin password
- `UPTIME_KUMA_API_VERSION=2` - Use v2 API for newer Uptime Kuma versions

## Adding a New Proxied Service

### Step 1: Check for Sample Config
```bash
cd /mnt/e/Docker/swag/config/nginx/proxy-confs/
ls *sample | grep myservice
```

### Step 2: Create Configuration

**Option A: Copy from Sample**
```bash
cp myservice.subdomain.conf.sample myservice.subdomain.conf
# Edit as needed, usually works out of the box
```

**Option B: Create Custom Config**
```nginx
## Version 2025/11/29
server {
    listen 443 ssl;
    listen [::]:443 ssl;

    server_name myservice.*;

    include /config/nginx/ssl.conf;

    client_max_body_size 0;

    location / {
        include /config/nginx/proxy.conf;
        include /config/nginx/resolver.conf;
        set $upstream_app myservice;
        set $upstream_port 8080;
        set $upstream_proto http;
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }
}
```

### Step 3: Reload Nginx
```bash
docker exec swag nginx -s reload
```

### Step 4: Test
```bash
curl -I https://myservice.benlawson.dev
```

## Common Configuration Patterns

### WebSocket Support
Add to location block:
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

### Large File Uploads
```nginx
client_max_body_size 0;  # Unlimited
```

### Custom Upstream Port
```nginx
set $upstream_app myservice;
set $upstream_port 8080;  # Change as needed
```

### Multiple Locations
```nginx
location / {
    # Main app
    proxy_pass http://myservice:8080;
}

location /api {
    # API endpoint
    proxy_pass http://myservice-api:3000;
}
```

### External IP (Non-Docker)
```nginx
set $upstream_proto http;
proxy_pass http://192.168.50.216:8080;
```

## Docker Socket Proxy Integration

SWAG uses `socket-proxy` for secure Docker API access (swag-ondemand mod):

```yaml
environment:
  - DOCKER_HOST=tcp://socket-proxy:2375
networks:
  - socket-proxy-net  # For Docker socket access
  - proxynet          # For routing to services
```

### On-Demand Containers

Services configured with `swag_ondemand=enable` label will:
1. Stop after 10 minutes of inactivity
2. Auto-start when accessed via SWAG
3. Show "Waking Up..." page during startup

**Example Service Labels:**
```yaml
labels:
  - swag_ondemand=enable
  - swag_ondemand_urls=https://myservice.
```

**⚠️ CRITICAL: Monitoring Compatibility**

**DO NOT monitor on-demand containers with Uptime Kuma or other uptime monitors!** Health check traffic counts as "access" and resets the inactivity timer, preventing containers from ever stopping. On-demand containers should only be accessed by actual users, not automated monitoring.

If you need to monitor availability:
- Monitor the SWAG proxy itself (always running)
- Use Docker health checks (doesn't trigger access logs)
- Accept that on-demand containers may be sleeping

**Log Monitoring:**
```bash
# Watch on-demand activity
docker exec swag tail -f /config/log/ondemand/ondemand.log

# Check last access time (should show "Stopped" events after 10min inactivity)
docker exec swag cat /config/log/ondemand/ondemand.log | tail -20
```

**Timeout Configuration:**
```yaml
# In docker-compose.yml, adjust stop threshold (default: 600 seconds)
environment:
  - SWAG_ONDEMAND_STOP_THRESHOLD=600  # 10 minutes
```

## SSL/TLS Configuration

### Wildcard Certificate
- **Domain**: *.benlawson.dev
- **Validation**: Cloudflare DNS
- **Renewal**: Automatic (checks daily at 2:08 AM)
- **Location**: `/mnt/e/Docker/swag/config/keys/`

### Check Certificate Status
```bash
docker exec swag certbot certificates
```

### Force Certificate Renewal
```bash
docker exec swag certbot renew --force-renewal
docker exec swag nginx -s reload
```

### Certificate Expiry
```bash
openssl x509 -in /mnt/e/Docker/swag/config/keys/letsencrypt/fullchain.pem -noout -dates
```

## Dashboard Access

SWAG Dashboard provides analytics via swag-dashboard mod:
- **URL**: https://dashboard.benlawson.dev
- **Features**: Request stats, bandwidth, top pages, status codes
- **Data Source**: Parses nginx access logs
- **Refresh**: Real-time with GoAccess

## Security Features

### fail2ban
- **Location**: `/mnt/e/Docker/swag/config/fail2ban/`
- **Default**: Enabled for nginx, common attacks
- **Logs**: `/config/log/fail2ban/`
- **Unban**: `docker exec swag fail2ban-client set nginx-http-auth unbanip <IP>`

### ModSecurity
- **Location**: `/mnt/e/Docker/swag/config/modsecurity/`
- **Rules**: OWASP Core Rule Set
- **Mode**: Detection only by default

### Rate Limiting
Configure in proxy config:
```nginx
limit_req_zone $binary_remote_addr zone=mylimit:10m rate=10r/s;
limit_req zone=mylimit burst=20 nodelay;
```

## Networking

### Network Routing
SWAG can reach services on ANY Docker network via container name:
- Services on `proxynet` - Direct routing
- Services on other networks - Docker's internal DNS resolves across networks

### Default Server Behavior
Undefined domains return 444 (connection closed):
```nginx
server {
    listen 443 ssl default_server;
    server_name _;
    return 444;
}
```
This enables Uptime Kuma to properly detect missing proxy configs as DOWN.

## Troubleshooting

### Nginx Won't Reload
```bash
# Test config syntax
docker exec swag nginx -t

# Check error log
docker exec swag tail -50 /config/log/nginx/error.log
```

### Service Not Accessible
1. **Check container is running**: `docker ps | grep myservice`
2. **Test internal connectivity**: `docker exec swag curl http://myservice:8080`
3. **Verify proxy config**: `docker exec swag cat /config/nginx/proxy-confs/myservice.subdomain.conf`
4. **Check SWAG logs**: `docker logs swag --tail 50`

### SSL Certificate Issues
```bash
# Check certificate status
docker exec swag certbot certificates

# Verify Cloudflare DNS token
docker exec swag cat /config/dns-conf/cloudflare.ini

# Manual renewal test
docker exec swag certbot renew --dry-run
```

### On-Demand Not Working
```bash
# Check on-demand logs
docker exec swag tail -50 /config/log/ondemand/ondemand.log

# Verify socket-proxy connectivity
docker exec swag curl http://socket-proxy:2375/containers/json

# Check container labels
docker inspect myservice | grep swag_ondemand
```

## Maintenance Tasks

### Update SWAG Container
```bash
cd /mnt/e/Docker/swag
docker compose pull
docker compose up -d
```

### Backup Configuration
```bash
tar -czf swag-config-backup-$(date +%Y%m%d).tar.gz /mnt/e/Docker/swag/config/nginx/
```

### View Active Connections
```bash
docker exec swag netstat -an | grep :443 | grep ESTABLISHED | wc -l
```

### Check Upstream Status
```bash
# View all configured upstreams
docker exec swag grep -r "set \$upstream_app" /config/nginx/proxy-confs/*.conf
```

## Best Practices

1. **Use Samples**: Always check for `.sample` files before creating custom configs
2. **Test Configs**: Run `nginx -t` before reloading
3. **Monitor Logs**: Check `/config/log/nginx/error.log` for issues
4. **Version Headers**: Add version comments to custom configs for tracking
5. **Backup Configs**: Keep backups before major changes
6. **Security First**: Enable fail2ban, use strong SSL settings
7. **Container Names**: Upstream app names must match Docker container names exactly
8. **Network Access**: Ensure services are on `proxynet` or Docker DNS can resolve them

## Common Proxy Configurations

### Media Services (Plex, Sonarr, Radarr)
- Usually have excellent sample configs
- Enable websockets
- Set appropriate `client_max_body_size`

### Authentication Required (Portainer, Homepage)
- Add auth middleware or use service's built-in auth
- Consider IP whitelisting for admin panels

### API Services (n8n, Ollama)
- Enable CORS if needed
- Set longer timeouts for LLM requests
- Configure appropriate body size limits

### Gaming Server UIs (Valheim, Minecraft)
- WebSocket support essential
- Consider on-demand for resource savings
- Handle long-running connections

## Related Components

- **socket-proxy**: Provides secure Docker API access for on-demand mod
- **Cloudflare**: DNS provider for Let's Encrypt validation
- **Uptime Kuma**: Monitors proxy endpoints for availability
- **Homepage**: Displays all proxied services with widgets
- **fail2ban**: Blocks malicious IPs automatically

## Reference Links

- [SWAG Documentation](https://docs.linuxserver.io/images/docker-swag/)
- [swag-dashboard Mod](https://github.com/linuxserver/docker-mods/tree/swag-dashboard)
- [swag-ondemand Mod](https://github.com/linuxserver/docker-mods/tree/swag-ondemand)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Let's Encrypt](https://letsencrypt.org/)
