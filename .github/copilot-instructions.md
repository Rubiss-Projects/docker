# Copilot Instructions

## Project Overview

This is a Docker-based home lab infrastructure managing 30+ self-hosted services across categories: Media (Plex, Sonarr, Radarr), Infrastructure (Nginx Proxy Manager, Bitwarden), Gaming (Valheim, Minecraft, ARK), and Observability (Prometheus, Grafana). Each service is deployed as an independent Docker Compose stack in its own directory.

## Architecture Patterns

### Service Organization
- **One service per directory**: Each folder contains a complete docker-compose.yml with its dependencies
- **Shared networking**: All services connect to the `proxynet` external network for internal communication
- **Consistent labeling**: Homepage integration labels follow strict patterns for service discovery

### Volume Mounting Conventions
- **Windows paths**: All volumes use `E:\Docker\{service}\{type}` pattern (e.g., `E:\Docker\plex\config:/config`)
- **Media paths**: Shared media volumes use `E:\Media\{type}` (movies, tv, videos, channels-dvr)
- **WSL compatibility**: Some services (like ARK) must run from WSL due to filesystem performance

### Environment Configuration
- **Per-service .env files**: Each service has its own `.env` file in the service directory
- **Global variables**: Common variables like PUID, PGID, TZ are repeated across services
- **Service-specific env files**: Some services use custom .env names (e.g., `db.env` for database configs)

## Service Categories & Labels

### Homepage Integration
**Docker services** use consistent homepage labels for dashboard integration:
```yaml
labels:
  - homepage.group={Media|Infrastructure|Gaming|Observability}
  - homepage.name={Service Name}
  - homepage.icon={service}.png
  - homepage.href=https://{service}.benlawson.dev/
  - homepage.description={Brief description}
```

**Non-Docker services** are configured in `homepage/config/services.yaml`:
```yaml
- Infrastructure:
    - Homebridge:
        icon: homebridge.png
        href: http://homebridge.benlawson.dev
        siteMonitor: http://192.168.50.40:8581
        description: Homekit integrations
        widget:
          type: homebridge
          url: http://192.168.50.40:8581
```

### Widget Configuration
Docker services use label-based widget configuration:
```yaml
- homepage.widget.type={service_type}
- homepage.widget.url=http://{container_name}:{port}
- homepage.widget.key=${HOMEPAGE_WIDGET_KEY}
```

Non-Docker services (HDHomeRun, Homebridge) define widgets directly in `services.yaml` with specific field configurations and direct IP addresses.

## Network Architecture

### External Network Pattern
All services connect to `proxynet` network:
```yaml
networks:
  proxynet:
    name: proxynet
```

### Port Management
- **Nginx Proxy Manager**: Handles external SSL termination (80, 443, 81)
- **Internal services**: Use non-standard ports to avoid conflicts
- **Gaming servers**: Use UDP port ranges (e.g., Valheim: 2456-2457/udp)

## Special Configurations

### GPU Services (Plex)
NVIDIA GPU passthrough for hardware transcoding:
```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu, compute, utility, video]
volumes:
  - /usr/lib/wsl/drivers:/usr/lib/wsl/drivers:ro
  - /usr/lib/wsl/lib:/usr/lib/wsl/lib:ro
```

### Gaming Servers
- **Resource management**: Use `cap_add: [sys_nice]` for scheduling priority
- **Graceful shutdown**: Extended `stop_grace_period` for save operations
- **Platform-specific**: ARK requires WSL execution for performance

### Database Services
Multi-container services use `depends_on` for startup ordering (e.g., Bitwarden + PostgreSQL).

## Development Workflows

### Adding New Services
1. **Docker services**: Create service directory: `mkdir {service-name}`
2. Copy docker-compose template with standard patterns
3. Configure volumes following `E:\Docker\{service}\{type}` convention
4. Add to `proxynet` network
5. Include homepage labels for dashboard integration

**Non-Docker services**: Add to `homepage/config/services.yaml` with direct IP addresses and widget configurations

### Environment Variables
- Copy `.env` file from similar service as template
- Use consistent variable names across services (PUID, PGID, TZ)
- Database services use separate `db.env` files

### Troubleshooting
- Check container logs: `docker logs {container_name}`
- Network connectivity: All services should reach each other via container names
- Volume permissions: Ensure PUID/PGID match host filesystem permissions