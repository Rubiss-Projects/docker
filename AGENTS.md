# AGENTS.md

## Project Overview

This is a Docker-based home lab infrastructure managing 30+ self-hosted services across categories: Media (Plex, Sonarr, Radarr), Infrastructure (SWAG Reverse Proxy, Bitwarden), Gaming (Valheim, Minecraft, ARK), and Observability (Prometheus, Grafana). Each service is deployed as an independent Docker Compose stack in its own directory.

## Service Guidance Index

Use the nearest applicable `AGENTS.md` for the task:

| Task / Service | Guidance Location |
|----------------|-------------------|
| **Adding a new service** | this file, under "New Service Setup" |
| **Uptime Kuma monitoring** | `uptime-kuma/AGENTS.md` |
| **Servarr stack** (Sonarr, Radarr, Prowlarr, Bazarr, Bookshelf, Seerr) | `sonarr/AGENTS.md`, `radarr/AGENTS.md`, `prowlarr/AGENTS.md`, `bazarr/AGENTS.md`, `bookshelf/AGENTS.md`, `bookshelf-audio/AGENTS.md`, `seerr/AGENTS.md` |
| **Calibre** | `calibre/AGENTS.md` |
| **Actual Budget** | `actual/AGENTS.md`, `actual-ai/AGENTS.md` |
| **n8n workflows** | `n8n/AGENTS.md` |
| **OpenClaw AI Gateway** | `openclaw/AGENTS.md` |
| **autobrr** | `autobrr/AGENTS.md` |
| **Gaming servers** | See individual: `valheim/AGENTS.md`, `minecraft/AGENTS.md`, `ark/AGENTS.md`, `palworld/AGENTS.md` |
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
- **SWAG**: Handles external SSL termination and reverse proxy (80, 443)
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

## Terminal Commands

**Important**: Avoid multiline commands in the terminal for this WSL/Docker Desktop environment. The WSL/Docker Desktop environment does not handle them correctly. Always use single-line commands with `&&` to chain operations or `;` to separate commands.

**Avoid:**
```bash
cat > file.txt << 'EOF'
content
EOF
```

**Prefer:**
```bash
echo 'content' > file.txt
```

For complex operations, create a script file first, then execute it.

## Troubleshooting
- Check container logs: `docker logs {container_name}`
- Network connectivity: All services should reach each other via container names
- Volume permissions: Ensure PUID/PGID match host filesystem permissions

# New Service Setup

This guide covers all steps required when adding a new Docker service to the infrastructure.

## Pre-Setup Questions

Before starting, determine:
1. **Pi service?** - Is this running on the Raspberry Pi (`/pi/` folder)?
2. **External access?** - Does it need a public URL via SWAG reverse proxy?

---

## Step 1: Create Service Directory

**Critical**: Folder name MUST match `container_name` exactly.

```bash
# Example for a service called "myservice"
mkdir /mnt/e/Docker/myservice
cd /mnt/e/Docker/myservice
```

This naming convention is required for:
- n8n workflow automations (container restart on failure)
- Uptime Kuma notifications with direct container links
- Consistent service discovery

---

## Step 2: Create docker-compose.yml

### Standard Template

```yaml
services:
  myservice:
    image: vendor/myservice:latest
    container_name: myservice  # MUST match folder name
    environment:
      - PUID=${PUID}
      - PGID=${PGID}
      - TZ=${TZ}
    volumes:
      - ./config:/config
    ports:
      - "8080:8080"
    restart: unless-stopped
    env_file:
      - .env
    networks:
      - proxynet
    labels:
      # Homepage integration - see Step 5
      - homepage.group=Media
      - homepage.name=My Service
      - homepage.icon=myservice.png
      - homepage.href=https://myservice.benlawson.dev/
      - homepage.description=Service description

networks:
  proxynet:
    external: true
    name: proxynet
```

### Network Configuration

**Always** add `proxynet` network:
```yaml
networks:
  proxynet:
    external: true
    name: proxynet
```

This enables:
- Internal communication between containers via hostname
- SWAG reverse proxy access
- Homepage widget connectivity

---

## Step 3: Create .env File

Create `.env` with secrets and configuration:

```bash
# Standard variables
PUID=1000
PGID=1000
TZ=America/Chicago

# Service-specific secrets
API_KEY=your-api-key-here
DATABASE_PASSWORD=secure-password
```

### Security: git-crypt

All `.env` files are encrypted with **git-crypt**. Ensure:
1. git-crypt is configured in the repository
2. Never commit secrets in plain text
3. Add new `.env` files to `.gitattributes` if needed:
   ```
   **/.env filter=git-crypt diff=git-crypt
   **/db.env filter=git-crypt diff=git-crypt
   ```

---

## Step 4: Configure SWAG Reverse Proxy

For external access, create a proxy configuration:

1. **Location**: `/mnt/e/Docker/swag/config/nginx/proxy-confs/`
2. **Create proxy config** (copy from sample or create new):
   ```bash
   cd /mnt/e/Docker/swag/config/nginx/proxy-confs/
   cp myservice.subdomain.conf.sample myservice.subdomain.conf
   ```
3. **Edit configuration**:
   - Set `server_name myservice.*;`
   - Set upstream: `set $upstream_app myservice;`
   - Set port: `set $upstream_port 8080;`
   - Enable websockets if needed
4. **Reload SWAG**:
   ```bash
   docker exec swag nginx -s reload
   ```

---

## Step 5: Add Homepage Integration

### Docker Services (Preferred Method)

Add labels to `docker-compose.yml`:

```yaml
labels:
  - homepage.group=Media              # Category: Media|Infrastructure|Gaming|Observability|Management
  - homepage.name=My Service          # Display name
  - homepage.icon=myservice.png       # Icon from dashboard-icons or /icons/
  - homepage.href=https://myservice.benlawson.dev/
  - homepage.siteMonitor=http://myservice:8080
  - homepage.description=Brief description
```

### With Official Widget

Check https://gethomepage.dev/widgets/ for available widgets. Always prefer official widgets:

```yaml
labels:
  - homepage.widget.type=myservice
  - homepage.widget.url=http://myservice:8080
  - homepage.widget.key=${API_KEY}
```

### Pi Services (Manual Configuration)

Services in `/pi/` folder must be added manually to `homepage/config/services.yaml`:

```yaml
- Infrastructure:
    - My Pi Service:
        icon: myservice.png
        href: http://myservice.benlawson.dev
        siteMonitor: http://192.168.50.40:8080
        description: Service on Raspberry Pi
        widget:
          type: myservice
          url: http://192.168.50.40:8080
```

### Custom Icons

If icon not in default set:
1. Save PNG to `homepage/config/icons/myservice.png`
2. Reference: `homepage.icon=/icons/myservice.png`

---

## Step 6: Add Uptime Kuma Monitor

Monitoring is automated via the `swag-auto-uptime-kuma` mod. Add labels to `docker-compose.yml` to create monitors automatically.

### Basic Monitor
```yaml
labels:
  - swag.uptime-kuma.enabled=true
  - swag.uptime-kuma.monitor.url=http://myservice:8080
  - swag.uptime-kuma.monitor.parent=Media  # Category in Uptime Kuma
```

### Advanced Configuration

**Custom Status Codes**:
```yaml
labels:
  - swag.uptime-kuma.monitor.accepted_statuscodes=200-299,401
```

**Auth Headers (e.g., Watchtower)**:
```yaml
labels:
  - swag.uptime-kuma.monitor.headers={"Authorization": "Bearer $${API_TOKEN}"}
```
*Note: Use double `$$` for environment variables in labels.*

### Port Mapping Note

Use **internal Docker ports**, not host-mapped ports:
- Good: `http://myservice:8080` (internal)
- Avoid: `http://myservice:8090` (host-mapped)

---

## Step 8: Start the Service

```bash
cd /mnt/e/Docker/myservice
docker compose up -d
```

**Important**: Always start from WSL for proper path registration.

---

## Step 9: Verify Setup

- [ ] Container running: `docker ps | grep myservice`
- [ ] Logs clean: `docker logs myservice`
- [ ] Internal access: `curl http://localhost:8080`
- [ ] Proxy working: `https://myservice.benlawson.dev`
- [ ] Homepage shows service with working widget
- [ ] Uptime Kuma monitor shows "Up"

---

## Quick Reference

| Step | Action | Required |
|------|--------|----------|
| 1 | Folder name = container_name | Always |
| 2 | docker-compose.yml with proxynet | Always |
| 3 | .env file with git-crypt | If secrets |
| 4 | SWAG proxy config | If external access |
| 5 | Homepage labels/config | Always |
| 6 | Uptime Kuma monitor | Always |
