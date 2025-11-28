# Copilot Instructions

## Project Overview

This is a Docker-based home lab infrastructure managing 30+ self-hosted services across categories: Media (Plex, Sonarr, Radarr), Infrastructure (Nginx Proxy Manager, Bitwarden), Gaming (Valheim, Minecraft, ARK), and Observability (Prometheus, Grafana). Each service is deployed as an independent Docker Compose stack in its own directory.

## Instructions Index

Navigate to the appropriate instructions file based on the task:

| Task / Service | Instructions File |
|----------------|-------------------|
| **Adding a new service** | `new-service-setup.instructions.md` |
| **Uptime Kuma monitoring** | `uptime-kuma.instructions.md` |
| **Servarr stack** (Sonarr, Radarr, Prowlarr, Bazarr, Bookshelf, Seerr) | `servarr.instructions.md` |
| **Calibre** | `calibre.instructions.md` |
| **Kavita** | `kavita.instructions.md` |
| **n8n workflows** | `n8n.instructions.md` |
| **Gaming servers** | See individual: `valheim`, `minecraft`, `ark`, `palworld` |
| **Pi services** | See individual in `/pi/` folder |

## Architecture Patterns

### Service Organization
- **One service per directory**: Each folder contains a complete docker-compose.yml with its dependencies
- **Naming Convention**: Folder name MUST match `container_name` (required for n8n automations and Uptime Kuma)
- **Shared networking**: All services connect to the `proxynet` external network for internal communication

### Volume Mounting Conventions
- **Relative paths**: All service volumes use relative paths (e.g., `./config:/config`) for portability and WSL compatibility
- **Media paths**: Shared media volumes use `../../Media/{type}` relative pattern (e.g., `../../Media/movies:/movies`)
- **WSL Execution**: ALL services must be started via WSL to ensure paths are registered correctly (e.g., `/mnt/e/Docker/...`)

### Environment & Secrets
- **Per-service .env files**: Each service has its own `.env` file in the service directory
- **git-crypt**: All `.env` and `db.env` files are encrypted using git-crypt. Never commit secrets in plain text.
- **Global variables**: Common variables like PUID, PGID, TZ are repeated across services

## Network Architecture

### External Network Pattern
All services MUST connect to `proxynet` network:
```yaml
networks:
  proxynet:
    external: true
    name: proxynet
```

### Port Management
- **Nginx Proxy Manager**: Handles external SSL termination (80, 443, 81)
- **Internal services**: Use non-standard ports to avoid conflicts
- **Uptime Kuma**: Always use internal Docker ports (not host-mapped)

## Homepage Integration

### Docker Services
Use labels in docker-compose.yml:
```yaml
labels:
  - homepage.group={Media|Infrastructure|Gaming|Observability|Management}
  - homepage.name={Service Name}
  - homepage.icon={service}.png
  - homepage.href=https://{service}.benlawson.dev/
  - homepage.description={Brief description}
  - homepage.widget.type={service_type}  # Check gethomepage.dev/widgets/
  - homepage.widget.url=http://{container_name}:{port}
  - homepage.widget.key=${API_KEY}
```

### Custom Icons
Save PNG to `homepage/config/icons/{service}.png`, reference as `homepage.icon=/icons/{service}.png`

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

### Database Services
Multi-container services use `depends_on` for startup ordering (e.g., Bitwarden + PostgreSQL).

## Troubleshooting
- Check container logs: `docker logs {container_name}`
- Network connectivity: All services should reach each other via container names
- Volume permissions: Ensure PUID/PGID match host filesystem permissions