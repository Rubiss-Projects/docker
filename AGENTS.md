# AGENTS.md

## Project Overview

This is a Docker-based home lab infrastructure managing 30+ self-hosted services across categories: Media (Plex, Sonarr, Radarr), Infrastructure (SWAG Reverse Proxy, Bitwarden), Gaming (Valheim, Minecraft, ARK), and Observability (Prometheus, Grafana). Each service is deployed as an independent Docker Compose stack in its own directory.

### Native BEN-SERVER

The main server now runs native Ubuntu at `/srv/Docker`; `/mnt/e/Docker` is a
compatibility path. Use the native deployment adapter described in
`scripts/native-deploy/README.md` to preserve the accepted restored volumes,
mount guards, image references and native settings. Keep the canonical native
checkout clean on `main` and release the native runner only after its policy
admission passes. Pi deployment remains separate.

Plex and Channels use host networking on BEN-SERVER; their accepted consumers
use explicit host aliases. The former native Caddy media proxy is retired.
New recurring backup infrastructure is outside the migration scope; preserve
the existing Lazywarden setup and retained migration recovery archives.

## Service Guidance Index

Use the nearest applicable `AGENTS.md` for the task:

| Task / Service | Guidance Location |
|----------------|-------------------|
| **Adding a new service** | this file, under "New Service Setup" |
| **Uptime Kuma monitoring** | `uptime-kuma/AGENTS.md` |
| **Servarr stack** (Sonarr, Radarr, Prowlarr, Bazarr, Bookshelf, Seerr) | `sonarr/AGENTS.md`, `radarr/AGENTS.md`, `prowlarr/AGENTS.md`, `bazarr/AGENTS.md`, `bookshelf/AGENTS.md`, `bookshelf-audio/AGENTS.md`, `seerr/AGENTS.md` |
| **Calibre** | `calibre/AGENTS.md` |
| **Sunday Edge workers** | `sunday-edge/AGENTS.md` |
| **n8n workflows** | `n8n/AGENTS.md` |
| **autobrr** | `autobrr/AGENTS.md` |
| **Gaming servers** | See individual: `valheim/AGENTS.md`, `minecraft/AGENTS.md`, `ark/AGENTS.md`, `palworld/AGENTS.md` |
| **Pi services** | See individual in `/pi/` folder |

## Architecture Patterns

### Changes to main and checkout hygiene

Use `.agents/skills/merge-to-main/SKILL.md` when preparing commits/PRs, merging,
or finishing repository work. All changes to `main` must go through a PR with
Codex automated review (at most five rounds, addressing actionable feedback).
Before any PR merge, and at the end of every task even without a PR, leave the
canonical `/mnt/e/Docker` checkout clean on `main`: the self-hosted deployment
runner uses this checkout. Prefer a separate feature worktree and never discard
someone else's work to satisfy this requirement.

### Service Organization
- **One service per directory**: Each folder contains a complete docker-compose.yml with its dependencies
- **Naming Convention**: Folder name MUST match `container_name` (required for n8n automations and Uptime Kuma)
- **Shared networking**: All services connect to the `proxynet` external network for internal communication

### Volume Mounting Conventions
- **Source defaults**: Compose files may retain relative-path defaults. On the main server, the admitted native policy selects the restored volumes and exact NAS paths; bypassing it can start an empty application state.
- **Media paths**: The verified NAS media tree is mounted at `/srv/Media`. Preserve the mount guard and accepted service mappings.
- **Host execution**: Run all main-server stacks, including `cadvisor`, through `scripts/native-deploy/compose.py`. Pi services retain their separate native Pi deployment.

### Environment & Secrets
- **Per-service .env files**: Each service has a public `.env` file for non-secret defaults in the service directory
- **Secret overlays**: Secrets live in encrypted `.env.secret` files (and `db.env.secret` for database services) loaded after `.env`
- **git-crypt**: All `.env.secret` files are encrypted using git-crypt. Never commit secrets in plain text.
- **Global variables**: Common variables like PUID, PGID, TZ are repeated across services

### Torrent Data Preservation
- **Explicit approval required**: Never remove a torrent, delete its data, or remove partially downloaded files without the user's explicit approval immediately before the destructive action.
- This applies even when a torrent is stalled, incomplete, duplicated, blocklisted, being replaced, has no seeders, or appears unlikely to finish.
- Adding or downloading a replacement does not authorize removal of the existing torrent or its data. Keep the original registered in the download client so it can continue downloading or seeding.
- Before any approved removal, report the exact torrent, completion percentage, current seed/peer availability, data path, and whether the data is recoverable.

## Network Architecture

### External Network Pattern
All services MUST connect to `proxynet` network:
```yaml
networks:
  proxynet:
    external: true
    name: proxynet
```

**Narrow exception — AI Assistant browser helper:** `ai-assistant-browser` is an
internal dependency of the `ai-assistant` stack and MUST remain off `proxynet`.
Its unauthenticated control API belongs only on the private `browser-control`
network shared with the assistant; publish no host port. Use `browser-egress` for
public internet access, retain its memory/swap limit, and mount no bot credentials
or data volumes. The main `ai-assistant` service remains on `proxynet`.

**Narrow exception — AI Assistant review helper:** `ai-assistant-reviewer` also
stays off `proxynet`, with no published port. Its control socket volume is shared
only with the assistant, outside agent workspaces. It uses `review-egress` for
Codex service traffic and its own ChatGPT login volume, never the assistant's
data/credentials or a Docker socket. Retain its memory/swap, CPU, and PID limits.
All three AI Assistant containers use the same immutable release version.

**Narrow exception — native media:** After the native storage migration, Plex
and Channels DVR use `network_mode: host` without published ports or a proxynet
attachment. Install the dedicated media INPUT guard first and preserve consumer
reachability. Use `scripts/native-media-network/README.md` for preparation,
acceptance and backout. Direct routes have passed acceptance; retain original
source data and rollback definitions without activating a second owner.

**Retired Caddy proxy:** Its source, systemd service and certificate timer are
retired. Do not install or start them during routine deployment. Plex uses direct
native access; Channels At Home uses the server's port 8089. Away From Home remains
deferred. Historical definitions remain available in Git history.

**Narrow exception — native Node Exporter:** `node-exporter/` uses host network
and PID namespaces to report BEN-SERVER's physical NIC and process metrics to
the same Node Exporter Full dashboard used by the Pi. It has no proxynet
attachment and listens only on `192.168.50.40:9100`; never add a public route.
Keep its host filesystem mounts read-only and its unprivileged user/capability
restrictions. Human host alerts use the existing Grafana notification channels.

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
Native NVIDIA GPU reservation for hardware transcoding:
```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu, compute, utility, video]
```

Use the installed native NVIDIA runtime and admitted Plex recipe. Do not add WSL
GPU library mounts. Verify GPU visibility in the container after a relevant change.

### Gaming Servers
- **Resource management**: Use `cap_add: [sys_nice]` for scheduling priority
- **Graceful shutdown**: Extended `stop_grace_period` for save operations

### Database Services
Multi-container services use `depends_on` for startup ordering (e.g., Bitwarden + PostgreSQL).

## Terminal Commands

Use single-line commands when crossing the Windows controller/SSH boundary.
For complex native operations, create an LF-terminated script and execute it
explicitly on the server. Run Git as the deployment account and preserve its
ownership; a root-owned index can break the runner.

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

## Native recovery

Docker requires the verified NAS media mount and admission guard. Preserve the
media firewall and assistant AppArmor ordering, the existing UPS guard, and the
reviewed Docker shutdown allowance. `native-https-startup.service` recovers the
existing admitted SWAG container and missing bridge attachments after Docker
setup; see `scripts/native-deploy/README.md`.

Inspect the failing service before taking action. Control-plane failure alone
must not interrupt working applications. The old Windows watchdog, WSL recovery
tasks and Caddy helpers are archived reference, not native recovery procedures;
see `docs/previous-host-operations.md`. Do not import their tasks or recovery loops.

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
    image: vendor/myservice:1.2.3@sha256:<verified-64-character-digest>
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
      - path: .env
      - path: .env.secret
        required: false
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

### Deployment Dependencies

If the service must start before or after another stack, update the dependency maps in `scripts/deploy-changed-service-folders.sh` so GitHub Actions deploys changed services in a safe order. Do not update or reinstall the retired Windows watchdog for native deployments.

For documentation-only or no-op repository hygiene changes, include `[skip deploy]` in the merge commit message to skip the self-hosted deploy jobs.

### Public Repository Actions Hardening

This repository uses self-hosted runners for deployment. Self-hosted deploy jobs must stay restricted to trusted pushes on `main`; do not add `pull_request`, `pull_request_target`, `workflow_run`, or public `workflow_dispatch` paths that can schedule jobs on `self-hosted` runners.

Required repository settings before making the repo public:
- GitHub Actions permissions: enabled, selected actions only, only `actions/checkout@*` allowlisted, third-party actions blocked unless explicitly reviewed and allowlisted, and actions pinned to full-length commit SHAs.
- Workflow permissions: read-only `GITHUB_TOKEN`; workflows cannot create or approve pull requests.
- Fork PR workflow approval: require approval for `all_external_contributors` after the repository becomes public.

After changing the repository to public, set the strict fork-PR approval policy:

```bash
gh api --method PUT repos/Rubiss-Projects/docker/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors
```

---

## Step 3: Create Environment Files

Create `.env` with public, non-secret defaults:

```bash
# Standard variables
PUID=1000
PGID=1000
TZ=America/Chicago
```

Create `.env.secret` for service-specific secrets:

```bash
API_KEY=your-api-key-here
DATABASE_PASSWORD=secure-password
```

### Security: git-crypt

All `.env.secret` files are encrypted with **git-crypt**. Ensure:
1. git-crypt is configured in the repository
2. Never commit secrets in plain text
3. Add new secret env patterns to `.gitattributes` if needed:
   ```
   *.env.secret filter=git-crypt diff=git-crypt
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

## Step 7: Add Dependabot Updates

Add the service to `.github/dependabot.yml` so Docker image pins continue to receive update PRs.

Use the same weekly Saturday schedule and labels as the existing service entries,
with an unused five-minute slot after the existing entries (currently 10:15).
Pin each image as `tag@sha256:digest`; prefer plain stable version tags, including
three-part numeric aliases for LinuxServer images. See [the image update policy](docs/image-updates.md).
Services built from a Dockerfile need a `docker` ecosystem entry for its directory;
a `docker-compose` entry alone does not update `FROM` images.

```yaml
  - package-ecosystem: docker-compose
    directory: /myservice
    schedule:
      interval: weekly
      day: saturday
      time: "10:15"
      timezone: America/Chicago
    open-pull-requests-limit: 1
    commit-message:
      prefix: deps
      include: scope
    labels:
      - dependencies
      - docker-compose
    groups:
      myservice-images:
        patterns:
          - '*'
```

Use the service directory as the `directory` value and a unique group name such as `{service}-images`.

---

## Step 8: Start the Service

```bash
cd /srv/Docker
python3 scripts/native-deploy/compose.py --stack myservice -- up -d
```

First release the new stack through reviewed native policy admission. The adapter
loads `.env` and an existing `.env.secret`, including substitutions used in labels.
Pi stacks use their separate deployment helper. Do not bypass admission with a
raw main-server Compose invocation.

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
| 3 | Public `.env` plus encrypted `.env.secret` | If secrets |
| 4 | SWAG proxy config | If external access |
| 5 | Homepage labels/config | Always |
| 6 | Uptime Kuma monitor | Always |
| 7 | Dependabot docker-compose entry | Always |
