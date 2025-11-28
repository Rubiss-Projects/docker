---
applyTo: "homepage/**"
---

# Homepage Dashboard Expert Instructions

You are an expert in Homepage dashboard configuration for service discovery and monitoring.

## Service Overview
Homepage is a modern, customizable application dashboard that integrates with Docker and various services to provide a unified view of your home lab. It displays service status, widgets, and links.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "3001:3000"
volumes:
  - ./config:/app/config
  - ./config/icons:/app/public/icons # Required for custom icons
  - /var/run/docker.sock:/var/run/docker.sock:ro
environment:
  - PUID=1000
  - PGID=1000
networks:
  - proxynet
restart: unless-stopped
```

### Critical Files
- `config/services.yaml` - Service definitions and widgets
- `config/settings.yaml` - Global settings
- `config/widgets.yaml` - Dashboard-wide widgets
- `config/bookmarks.yaml` - Bookmark links
- `config/docker.yaml` - Docker service discovery config

### Default Port
- 3001 (mapped from container's 3000)

## Configuration Structure

### services.yaml
Defines services organized into groups:
```yaml
## Configuration Structure

### services.yaml
Defines services organized into groups:
```yaml
- Media:
    - Plex:
        icon: plex.png
        href: https://plex.benlawson.dev
        description: Media server
        widget:
          type: plex
          url: http://plex:32400
          key: YOUR_PLEX_TOKEN
```

## Custom Icons
To use custom icons not included in the default set:
1.  **Storage**: Place PNG files in `config/icons/`
2.  **Mount**: Ensure `docker-compose.yml` mounts `./config/icons:/app/public/icons`
3.  **Usage**: Reference as `/icons/filename.png` in labels or config
    - Label: `homepage.icon=/icons/myicon.png`
    - Config: `icon: /icons/myicon.png`

    - Sonarr:
        icon: sonarr.png
        href: https://sonarr.benlawson.dev
        description: TV show management
        widget:
          type: sonarr
          url: http://sonarr:8989
          key: YOUR_SONARR_API_KEY

- Infrastructure:
    - Nginx Proxy Manager:
        icon: nginx-proxy-manager.png
        href: http://localhost:81
        description: Reverse proxy
        
- Raspberry Pi:
    - Homebridge:
        icon: homebridge.png
        href: http://192.168.50.216:8581
        description: HomeKit integrations
        widget:
          type: homebridge
          url: http://192.168.50.216:8581
          username: admin
          password: ${HOMEBRIDGE_PASSWORD}
```

## Docker Service Discovery

### Automatic Discovery via Labels
Add labels to service's docker-compose.yml:
```yaml
labels:
  - homepage.group=Media
  - homepage.name=Plex
  - homepage.icon=plex.png
  - homepage.href=https://plex.benlawson.dev
  - homepage.description=Media streaming server
  - homepage.widget.type=plex
  - homepage.widget.url=http://plex:32400
  - homepage.widget.key=${PLEX_TOKEN}
```

### Enable Docker Discovery
In `config/docker.yaml`:
```yaml
my-docker:
  socket: /var/run/docker.sock
```

### Docker Socket Permissions
Must mount Docker socket read-only:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
```

## Widget Types and Configuration

### Docker Container Widget
Shows container status, CPU, RAM:
```yaml
widget:
  type: docker
  container: container_name  # Optional, auto-detected if using labels
```

### Plex
```yaml
widget:
  type: plex
  url: http://plex:32400
  key: YOUR_PLEX_TOKEN  # Get from: Settings > Network > Show Advanced
```

### Sonarr/Radarr/Prowlarr (Servarr)
```yaml
widget:
  type: sonarr  # or radarr, prowlarr
  url: http://sonarr:8989
  key: YOUR_API_KEY  # Settings > General > API Key
```

### Pi-hole
```yaml
widget:
  type: pihole
  url: http://192.168.50.216:80
  key: YOUR_PIHOLE_API_KEY  # From setupVars.conf
  fields: ["queries", "blocked", "blocked_percent"]
```

### Homebridge
```yaml
widget:
  type: homebridge
  url: http://192.168.50.216:8581
  username: admin
  password: ${HOMEBRIDGE_PASSWORD}
```

### Prometheus
```yaml
widget:
  type: prometheus
  url: http://prometheus:9090
```

### Generic API
```yaml
widget:
  type: customapi
  url: http://service:port/api/endpoint
  headers:
    Authorization: Bearer YOUR_TOKEN
  display: "{{data.field}}"
```

## Common Tasks

### Add New Service
**Option 1: Manual (services.yaml)**
```yaml
- GroupName:
    - ServiceName:
        icon: service.png
        href: https://service.benlawson.dev
        description: Service description
```

**Option 2: Docker Labels**
Add to service's docker-compose.yml, Homepage auto-discovers.

### Add Widget to Service
```yaml
- ServiceName:
    # ... other config
    widget:
      type: widget_type
      url: http://service:port
      key: ${API_KEY}  # Use env vars for secrets
```

### Organize Services into Groups
```yaml
- Infrastructure:
    - Service1:
        # config
    - Service2:
        # config

- Media:
    - Service3:
        # config
```

### Add Bookmarks
In `config/bookmarks.yaml`:
```yaml
- Developer:
    - GitHub:
        - icon: github.png
          href: https://github.com
    - GitLab:
        - icon: gitlab.png
          href: https://gitlab.com

- Homelab:
    - Proxmox:
        - icon: proxmox.png
          href: https://proxmox.local:8006
```

### Configure Dashboard Widgets
In `config/widgets.yaml`:
```yaml
- logo:
    icon: https://github.com/walkxcode/dashboard-icons/blob/main/png/homer.png

- search:
    provider: google
    target: _blank

- datetime:
    text_size: xl
    format:
      timeStyle: short
      dateStyle: short
```

## Integration Points

### Nginx Proxy Manager
```
Domain: homepage.benlawson.dev
Forward: http://homepage:3000
Websockets: Yes
SSL: Let's Encrypt
```

### Docker Services
- Use container names for URLs (e.g., `http://plex:32400`)
- All services must be on `proxynet` network
- Docker socket enables automatic service discovery

### Environment Variables
Store sensitive data in `.env`:
```bash
PLEX_TOKEN=your_token_here
SONARR_API_KEY=your_key_here
HOMEBRIDGE_PASSWORD=your_password
```

Reference in config:
```yaml
key: ${PLEX_TOKEN}
```

## Troubleshooting

### Widget Shows "Error" or "Unavailable"
1. Check service is running: `docker ps`
2. Verify URL is correct (use container name for Docker services)
3. Test API endpoint: `curl http://service:port/api`
4. Check API key/token is valid
5. Review Homepage logs: `docker logs homepage`

### Docker Services Not Auto-Discovered
1. Verify Docker socket is mounted: `docker inspect homepage`
2. Check `docker.yaml` configuration
3. Ensure labels are in correct format
4. Restart Homepage: `docker compose restart`

### Cannot Access Dashboard
1. Check port 3001 is exposed: `docker ps`
2. Test: `curl http://localhost:3001`
3. Check firewall settings
4. Review logs: `docker logs homepage`

### Widgets Load Slowly
1. Increase timeout in `settings.yaml`:
```yaml
providers:
  timeout: 10000  # 10 seconds
```
2. Check network connectivity to services
3. Optimize widget refresh rates

### Icons Not Displaying
1. Check icon name matches Dashboard Icons library
2. Use direct URL for custom icons
3. Verify internet connectivity for external icons
4. Check Homepage logs for 404 errors

## Best Practices

1. **Use Docker Labels**: Easier to manage than manual services.yaml
2. **Environment Variables**: Store secrets in .env file
3. **Group Logically**: Organize services by function (Media, Infrastructure, etc.)
4. **Descriptive Names**: Make service purposes clear
5. **Consistent Icons**: Use Dashboard Icons library for uniformity
6. **Test Widgets**: Verify API connectivity before deploying
7. **Backup Config**: Keep config directory in git
8. **Mobile-Friendly**: Test layout on mobile devices
9. **Performance**: Limit number of widgets to reduce load time
10. **Documentation**: Comment complex configurations

## Security Considerations

- **API Keys**: Never commit to git (use .env)
- **Docker Socket**: Mounted read-only to prevent container manipulation
- **Network Isolation**: Keep on proxynet, expose via NPM with auth
- **Authentication**: Enable auth in settings.yaml for external access
- **HTTPS**: Always use SSL when accessing remotely

## Advanced Configuration

### Custom Theme
In `config/settings.yaml`:
```yaml
theme: dark  # or light
color: zinc  # slate, gray, zinc, neutral, stone
```

### Custom Layout
```yaml
layout:
  Media:
    columns: 3  # Number of columns for Media group
    style: row  # or column
  Infrastructure:
    columns: 2
```

### Custom CSS
In `config/custom.css`:
```css
.service-card {
    border-radius: 10px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
```

### Authentication
In `config/settings.yaml`:
```yaml
providers:
  openweathermap: YOUR_API_KEY  # For weather widget

authentication:
  enabled: true
  users:
    - username: admin
      password: $2y$10$hashed_password_here
```

### Multi-Language
```yaml
language: en  # en, de, fr, es, etc.
```

## Widget Configuration Examples

### Transmission (Downloads)
```yaml
widget:
  type: transmission
  url: http://transmission:9091
  username: admin
  password: ${TRANSMISSION_PASSWORD}
```

### Bitwarden
```yaml
widget:
  type: bitwarden
  url: http://bitwarden:80
```

### Uptime Kuma
```yaml
widget:
  type: uptimekuma
  url: http://uptime-kuma:3001
  slug: your_slug_here
```

### Portainer
```yaml
widget:
  type: portainer
  url: http://portainer:9000
  env: 1  # Environment ID
  key: ${PORTAINER_API_KEY}
```

## Useful Widgets

### System Stats (Homepage Widget)
In `config/widgets.yaml`:
```yaml
- resources:
    cpu: true
    memory: true
    disk: /
```

### Search Bar
```yaml
- search:
    provider: google
    target: _blank
    focus: true  # Auto-focus on page load
```

### Weather
```yaml
- openweathermap:
    latitude: 40.7128
    longitude: -74.0060
    units: imperial  # or metric
    apiKey: ${OPENWEATHER_API_KEY}
```

## Monitoring Homepage Itself

### Health Check
```powershell
curl http://localhost:3001/api/healthcheck
```

### Logs
```powershell
docker logs homepage -f --tail 100
```

### Resource Usage
```powershell
docker stats homepage
# Should be ~50-100MB RAM
```

## Backup and Restore

### Backup Configuration
```powershell
tar -czf homepage-backup-$(Get-Date -Format "yyyyMMdd").tar.gz config/
```

### Restore Configuration
```powershell
tar -xzf homepage-backup-YYYYMMDD.tar.gz
docker compose restart
```

## Multi-Host Service Configuration

### Windows Docker Services
Use container names (Docker DNS):
```yaml
url: http://plex:32400
```

### Raspberry Pi Services
Use static IP addresses:
```yaml
url: http://192.168.50.216:8581
```

### Remote Services (Non-Docker)
Use direct IP or hostname:
```yaml
url: http://192.168.50.100:8080
```

## Performance Optimization

### Reduce Widget Refresh
In `config/settings.yaml`:
```yaml
providers:
  refresh: 60000  # 60 seconds (default: 10s)
```

### Disable Unused Features
```yaml
features:
  docker: true  # Disable if not using Docker discovery
  kubernetes: false
```

### Limit Service Count
- Keep dashboard focused (20-30 services max)
- Use multiple pages/groups if needed
- Hide rarely-used services

## Common Service Groups

### 📺 Media Consumption
Focus: Watching, reading, and listening.
- Plex, Channels DVR, Audiobookshelf, Kavita, Calibre

### ⚙️ Media Management
Focus: The arr stack and request tools.
- Seerr, Audiobook Request, Sonarr, Radarr, Bookshelf, Bookshelf-Audio, Bazarr, Prowlarr

### 🤖 AI & Automation
Focus: LLMs and workflows.
- Open WebUI, Ollama, n8n

### 🏗️ Infrastructure
Focus: Core networking and container management.
- Nginx Proxy Manager, Pi-hole, Cloudflare Tunnel, Portainer, Watchtower, Bitwarden, LazyWarden, Homebridge

### 📊 Observability
Focus: Monitoring and metrics.
- Grafana, Prometheus, InfluxDB, Uptime Kuma, Tautulli, Speedtest Tracker, Glances, cAdvisor

### 🖥️ Hardware
Focus: Physical hardware stats.
- NVIDIA GPU, HDHomeRun

This centralized dashboard provides at-a-glance status and quick access to all services across Windows and Raspberry Pi hosts.
