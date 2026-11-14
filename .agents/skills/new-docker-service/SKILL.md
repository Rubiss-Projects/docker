---
name: new-docker-service
description: "Step-by-step workflow for adding a new Docker service to the home lab infrastructure. Use when creating a new container, setting up a new self-hosted service, or onboarding any new Docker Compose stack. Covers directory setup, compose config, SWAG proxy, Homepage labels, Uptime Kuma monitoring, and Homelable inventory and topology."
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

## Step 7 — Register in Homelable and Update Topology

After deployment, register every new container, including databases and internal
helpers, in Homelable at <https://homelable.benlawson.dev:4443/>. Follow
`homelable/README.md` for access and monitoring policy. Use the existing shared
Bitwarden login without printing credentials or storing them in inventory notes.

1. Read the current designs, nodes and inventory first. Reuse an existing service
   entry if present; avoid duplicate devices or canvases. Back up the affected
   records before editing.
2. Add the service to the existing single home-lab canvas and nest its
   `docker_container` node under the machine actually running it (BEN-SERVER or
   the Raspberry Pi). Record the container name, Compose stack and useful access
   URL. Do not treat transient container IPs as stable host addresses.
3. Add directed, meaningfully labeled links from consumer to dependency, using
   verified Compose and live configuration: databases, caches, APIs, download
   clients, NAS storage, proxy upstreams and monitoring integrations as applicable.
   Update affected existing nodes too. Do not infer a dependency merely because
   two services share a Docker network; do not invent physical wiring.
4. Preserve manual positions, metadata and unrelated nodes/edges. Use incremental
   authenticated API operations or UI edits, not whole-canvas replacement. Keep
   related containers together and avoid repetitive LAN/Wi-Fi labels; connection
   details belong in device properties.
5. Leave new services' inventory check methods empty/null, not `none` (which
   reports online without probing). Keep Homelable service checks disabled;
   Uptime Kuma owns service availability. Preserve the existing machine-only
   checks. Review imported/scanned entries for automatically assigned ping checks.

Read back the saved records to verify host membership, dependency endpoints,
absence of duplicates and disabled service checks. If Homelable is unavailable,
report the outstanding registration explicitly rather than claiming onboarding
is complete. Apply the same topology maintenance when moving or retiring a
service; confirm retirement before removing its inventory entry.

---

## Step 8 — Verify

Run through this checklist before considering the service done:

- [ ] `docker ps | grep <service-name>` — container running
- [ ] `docker logs <service-name>` — no errors
- [ ] Internal access: `curl http://localhost:<host-port>`
- [ ] External access: `https://<service-name>.benlawson.dev` (if proxied)
- [ ] Homepage shows service (with working widget if configured)
- [ ] Uptime Kuma monitor appears and shows "Up"
- [ ] Homelable inventory and existing canvas include every new container under its actual host
- [ ] Verified dependency links are saved without duplicate nodes or unrelated layout changes
- [ ] Homelable service check methods remain empty; existing machine checks are preserved

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
| 7 | Homelable inventory and topology | Yes |
| 8 | Verify checklist | Yes |
