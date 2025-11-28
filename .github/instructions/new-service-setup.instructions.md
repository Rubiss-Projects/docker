---
applyTo: "**"
---

# New Service Setup Checklist

This guide covers all steps required when adding a new Docker service to the infrastructure.

## Pre-Setup Questions

Before starting, determine:
1. **Pi service?** - Is this running on the Raspberry Pi (`/pi/` folder)?
2. **External access?** - Does it need a public URL via Nginx Proxy Manager?

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
- Nginx Proxy Manager reverse proxy access
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

## Step 4: Configure Nginx Proxy Manager

For external access, add a proxy host:

1. **Login**: https://npm.benlawson.dev
2. **Add Proxy Host**:
   - Domain: `myservice.benlawson.dev`
   - Scheme: `http`
   - Forward Hostname: `myservice` (container name)
   - Forward Port: Internal port (e.g., `8080`)
   - Enable: Websockets Support (if needed)
3. **SSL**:
   - Request new SSL certificate
   - Force SSL
   - HTTP/2 Support

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

1. **Login**: https://uptime.benlawson.dev
2. **Add New Monitor**:
   - Monitor Type: HTTP(s)
   - Friendly Name: `myservice`
   - URL: `http://myservice:8080` (internal Docker URL)
   - Heartbeat Interval: 60 seconds
3. **Notifications**: Enable Discord and n8n notifications

### Port Mapping Note

Use **internal Docker ports**, not host-mapped ports:
- ✅ `http://myservice:8080` (internal)
- ❌ `http://myservice:8090` (host-mapped)

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
| 1 | Folder name = container_name | ✅ Always |
| 2 | docker-compose.yml with proxynet | ✅ Always |
| 3 | .env file with git-crypt | ✅ If secrets |
| 4 | Nginx Proxy Manager | If external access |
| 5 | Homepage labels/config | ✅ Always |
| 6 | Uptime Kuma monitor | ✅ Always |
