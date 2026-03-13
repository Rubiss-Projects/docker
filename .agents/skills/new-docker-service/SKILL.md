---
name: new-docker-service
description: "Step-by-step workflow for adding a new Docker service to the home lab infrastructure. Use when creating a new container, setting up a new self-hosted service, or onboarding any new Docker Compose stack. Covers directory setup, compose config, SWAG proxy, Homepage labels, and Uptime Kuma monitoring."
category: devops
---

# New Docker Service Setup

Guided workflow for adding a new service to the Docker home lab at `/mnt/e/Docker`.

---

## Pre-Flight Checklist

Before creating any files, answer these two questions:

1. **Pi service?** — Running on Raspberry Pi? → Use `/pi/` folder instead; follow Pi-specific steps.
2. **External access?** — Needs a public URL? → SWAG proxy config required (Step 4).

---

## Step 1 — Create the Service Directory

**CRITICAL**: Folder name MUST exactly match `container_name`. This is required for n8n automations and Uptime Kuma links.

```bash
mkdir /mnt/e/Docker/<service-name>
```

---

## Step 2 — Write `docker-compose.yml`

Use this template, filling in service-specific values:

```yaml
services:
  <service-name>:
    image: vendor/<service-name>:latest
    container_name: <service-name>   # Must match folder name
    environment:
      - PUID=${PUID}
      - PGID=${PGID}
      - TZ=${TZ}
    volumes:
      - ./config:/config
    ports:
      - "<host-port>:<container-port>"
    restart: unless-stopped
    env_file:
      - .env
    networks:
      - proxynet
    labels:
      # Homepage
      - homepage.group=<Media|Infrastructure|Gaming|Observability|Management>
      - homepage.name=<Display Name>
      - homepage.icon=<service-name>.png
      - homepage.href=https://<service-name>.benlawson.dev/
      - homepage.siteMonitor=http://<service-name>:<container-port>
      - homepage.description=<Brief description>
      # Uptime Kuma
      - swag.uptime-kuma.enabled=true
      - swag.uptime-kuma.monitor.url=http://<service-name>:<container-port>
      - swag.uptime-kuma.monitor.parent=<Media|Infrastructure|Gaming|Observability|Management>

networks:
  proxynet:
    external: true
    name: proxynet
```

### Key rules
- **Always** include the `proxynet` network block — required for SWAG, Homepage, and inter-container communication.
- **Never** use host-mapped ports in Uptime Kuma labels; use internal container ports.
- If a service has an official Homepage widget, add `homepage.widget.*` labels (check [gethomepage.dev/widgets](https://gethomepage.dev/widgets/)).

---

## Step 3 — Create `.env` File

```bash
# Standard
PUID=1000
PGID=1000
TZ=America/Chicago

# Service-specific secrets below
API_KEY=
```

**git-crypt**: All `.env` files are encrypted. If adding a new path pattern, update `.gitattributes`:
```
**/.env filter=git-crypt diff=git-crypt
```

---

## Step 4 — SWAG Proxy Config (external access only)

```bash
# Check for an existing sample first
ls /mnt/e/Docker/swag/config/nginx/proxy-confs/ | grep <service-name>

# Copy or create the conf
cp /mnt/e/Docker/swag/config/nginx/proxy-confs/<service-name>.subdomain.conf.sample \
   /mnt/e/Docker/swag/config/nginx/proxy-confs/<service-name>.subdomain.conf
```

Edit the conf file:
- `server_name <service-name>.*;`
- `set $upstream_app <service-name>;`
- `set $upstream_port <container-port>;`

Then reload SWAG:
```bash
docker exec swag nginx -s reload
```

---

## Step 5 — Homepage Widget (if official widget exists)

Add to compose labels:
```yaml
- homepage.widget.type=<service-name>
- homepage.widget.url=http://<service-name>:<container-port>
- homepage.widget.key=${API_KEY}   # Only if required
```

### Custom icon (if not in default icon set)
1. Save PNG to `homepage/config/icons/<service-name>.png`
2. Use `homepage.icon=/icons/<service-name>.png`

### Pi services — manual YAML entry
Pi services cannot use Docker labels. Edit `homepage/config/services.yaml` directly:
```yaml
- Infrastructure:
    - <Display Name>:
        icon: <service-name>.png
        href: http://<service-name>.benlawson.dev
        siteMonitor: http://192.168.50.40:<port>
        description: <Brief description>
```

---

## Step 6 — Start the Service

**Always start from WSL** for correct path registration:
```bash
cd /mnt/e/Docker/<service-name>
docker compose up -d
```

---

## Step 7 — Verify

Run through this checklist before considering the service done:

- [ ] `docker ps | grep <service-name>` — container running
- [ ] `docker logs <service-name>` — no errors
- [ ] Internal access: `curl http://localhost:<host-port>`
- [ ] External access: `https://<service-name>.benlawson.dev` (if proxied)
- [ ] Homepage shows service (with working widget if configured)
- [ ] Uptime Kuma monitor appears and shows "Up"

---

## Decision Tree

```
New service requested
│
├── Pi service? ──Yes──> Use /pi/<name>/ folder
│                        Add to homepage/config/services.yaml manually
│                        No Docker labels for Uptime Kuma
│
└── No
    ├── External access needed? ──Yes──> Create SWAG proxy conf (Step 4)
    │
    ├── Official Homepage widget? ──Yes──> Add homepage.widget.* labels
    │
    └── Custom icon needed? ──Yes──> Add PNG to homepage/config/icons/
```

---

## Quick Reference

| Step | File/Action | Always Required? |
|------|-------------|-----------------|
| 1 | `mkdir /mnt/e/Docker/<name>` | Yes |
| 2 | `docker-compose.yml` with proxynet + labels | Yes |
| 3 | `.env` with git-crypt | If secrets exist |
| 4 | SWAG proxy conf + reload | If external URL needed |
| 5 | Homepage widget labels | If widget available |
| 6 | `docker compose up -d` from WSL | Yes |
| 7 | Verify checklist | Yes |
