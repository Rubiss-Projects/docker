# Raspberry Pi 3 Docker Services

Docker Compose configurations for services running on Raspberry Pi 3 with Ubuntu Server, integrated with Windows Docker host for monitoring and management.

## 📋 Quick Start Guide

### Step 1: Human Setup (You)
Follow **[HUMAN-SETUP-GUIDE.md](./pi-setup/HUMAN-SETUP-GUIDE.md)** to:
- Flash Ubuntu Server to SD card
- Configure static IP (192.168.50.216)
- Install Git and clone this repo
- Set up VS Code tunnel

**Time:** ~30 minutes

### Step 2: AI Agent Setup (Automated)
Give **[AI-SETUP-INSTRUCTIONS.md](./pi-setup/AI-SETUP-INSTRUCTIONS.md)** to an AI agent to:
- Install Docker
- Deploy all 5 services
- Verify and test everything

**Time:** ~10 minutes

### Step 3: Windows Host Changes
See **[WINDOWS-CHANGES-SUMMARY.md](./pi-setup/WINDOWS-CHANGES-SUMMARY.md)** for:
- Prometheus configuration (already updated)
- Homepage dashboard (already updated)
- NPM proxy setup (manual steps)

**Note:** Prometheus and Homepage configs are already committed. Just restart Prometheus and configure NPM proxies.

---

---

## 🖥️ System Information

- **Device:** Raspberry Pi 3
- **OS:** Ubuntu Server 24.04.3 LTS (64-bit ARM)
- **RAM:** 1GB
- **Storage:** 32GB microSD
- **IP Address:** 192.168.50.216 (static)
- **Network:** Same subnet as Windows host (192.168.50.x/24)

---

## 🐳 Deployed Services

All services are deployed and managed automatically by the AI agent.

### Homebridge
**Purpose:** HomeKit integration for smart home devices  
**Port:** 8581 (Web UI)  
**Access:** http://192.168.50.216:8581 or https://homebridge.benlawson.dev

**Key Info:**
- Get PIN from logs: `docker logs homebridge | grep PIN`
- Default credentials: admin/admin (change on first login)
- Configure plugins through web interface

### Pi-hole
**Purpose:** Network-wide ad blocking and DNS  
**Port:** 80 (Web UI)  
**Access:** http://192.168.50.216/admin or https://pihole.benlawson.dev/admin

**Key Info:**
- Password set in `.env` file (default: changeme123 - CHANGE THIS!)
- Get API key: `docker exec pihole cat /etc/pihole/setupVars.conf | grep WEBPASSWORD`
- Configure router DNS to 192.168.50.216 for network-wide blocking

### Watchtower
**Purpose:** Automatic Docker container updates  
**Port:** None (runs in background)

**Key Info:**
- Checks for updates daily at 4 AM
- Updates and restarts containers automatically
- Check logs: `docker logs watchtower`

### cAdvisor (Monitoring)
**Purpose:** Docker container metrics for Prometheus  
**Port:** 8080 (Web UI and metrics endpoint)  
**Access:** http://192.168.50.216:8080

**Key Info:**
- Per-container CPU, memory, network, disk metrics
- Scraped by Prometheus on Windows host
- Optimized for Pi 3 performance

### node-exporter (Monitoring)
**Purpose:** System-level metrics for Prometheus  
**Port:** 9100 (metrics endpoint, no UI)  
**Access:** http://192.168.50.216:9100/metrics

**Key Info:**
- CPU, memory, disk, network metrics
- **Raspberry Pi temperature monitoring** (critical!)
- Scraped by Prometheus on Windows host

## Initial Pi Setup Commands

**Note:** These commands are automated in the AI-SETUP-INSTRUCTIONS.md. This section is for reference only.

### 1. Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Docker
```bash
# Install Docker
sudo apt install docker.io docker-compose -y

# Add user to docker group (replace 'pi' with your username)
sudo usermod -aG docker $USER

# Reboot to apply group changes
sudo reboot
```

### 3. Install Git
```bash
sudo apt install git -y
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### 4. Clone This Repo
```bash
cd ~
git clone https://github.com/Rubiss/docker.git
cd docker/pi
```

### 5. Install VS Code Tunnel (Optional)
```bash
# Download VS Code CLI for ARM64
curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-arm64' --output vscode_cli.tar.gz

# Extract
tar -xf vscode_cli.tar.gz

# Move to PATH
sudo mv code /usr/local/bin/

# Start tunnel
code tunnel
```

Follow authentication prompts, then access from VS Code on your PC via Remote Tunnels.

## Network Configuration

### Static IP (Required)
The Pi must have static IP **192.168.50.216** for integration with Windows services.

**Setup in router:**
1. Find Pi's MAC address: `ip addr show`
2. Create DHCP reservation in router for 192.168.50.216
3. Reboot Pi: `sudo reboot`

**Or configure directly on Pi using netplan** (see HUMAN-SETUP-GUIDE.md for details)

### Windows Host Integration
The following Windows services are **already configured** to work with the Pi at 192.168.50.216:

**Prometheus** (`E:\Docker\prometheus\config\prometheus.yml`):
- Scrapes cAdvisor metrics from Pi (port 8080)
- Scrapes node-exporter metrics from Pi (port 9100)

**Homepage Dashboard** (`E:\Docker\homepage\config\services.yaml`):
- Shows Homebridge widget (port 8581)
- Shows Pi-hole widget (port 80)  
- Shows Pi System Monitor link (cAdvisor port 8080)

**Nginx Proxy Manager**:
- Proxy `homebridge.benlawson.dev` → `192.168.50.216:8581`
- Proxy `pihole.benlawson.dev` → `192.168.50.216:80`

### DNS Setup (Pi-hole)
Once Pi-hole is running:
1. Test locally: `nslookup google.com 192.168.50.216`
2. Update router DNS settings to point to 192.168.50.216
3. Or manually set DNS on each device

## Service Management

### Start All Services
```bash
cd ~/docker/pi/homebridge && docker compose up -d
cd ~/docker/pi/pi-hole && docker compose up -d
cd ~/docker/pi/watchtower && docker compose up -d
cd ~/docker/pi/cadvisor && docker compose up -d
cd ~/docker/pi/node-exporter && docker compose up -d
```

**Or use the management script (created by AI agent):**
```bash
~/docker/pi/manage-services.sh start
```

### Stop All Services
```bash
cd ~/docker/pi/homebridge && docker compose down
cd ~/docker/pi/pi-hole && docker compose down
cd ~/docker/pi/watchtower && docker compose down
cd ~/docker/pi/cadvisor && docker compose down
cd ~/docker/pi/node-exporter && docker compose down
```

**Or:**
```bash
~/docker/pi/manage-services.sh stop
```

### View Logs
```bash
docker compose logs -f [service-name]
```

### Update Containers
```bash
docker compose pull
docker compose up -d
```

## Troubleshooting

### Pi-hole Port 80 Conflict
If port 80 is already in use:
```bash
sudo netstat -tulpn | grep :80
# Kill conflicting process or change Pi-hole port in docker-compose.yml
```

### Homebridge Not Discovering Devices
- Ensure network_mode: host is enabled (required for mDNS)
- Check firewall: `sudo ufw status`
- Restart container: `docker compose restart`

### Docker Permission Denied
```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in, or reboot
```

## Performance Notes

⚠️ **Pi 3 has 1GB RAM** - Keep it light:
- Run only essential services
- Monitor resource usage: `htop` or `docker stats`
- Consider disabling swap if SD card is slow
- Use lightweight base images when possible

## Backup Strategy

### Config Backups
```bash
# Backup Homebridge config
tar -czf homebridge-backup-$(date +%Y%m%d).tar.gz ~/docker/pi/homebridge/config

# Backup Pi-hole config
tar -czf pihole-backup-$(date +%Y%m%d).tar.gz ~/docker/pi/pi-hole/etc-pihole
```

### Restore Configs
```bash
# Extract to original location
tar -xzf backup-file.tar.gz -C ~/docker/pi/
```

## Security Considerations

- Change default passwords in `.env` files
- Keep system updated: `sudo apt update && sudo apt upgrade`
- Use strong SSH keys (disable password auth)
- Firewall: `sudo ufw enable` and allow only necessary ports
- Regular backups of configurations

## Useful Commands

```bash
# Check Pi temperature
vcgencmd measure_temp

# System resources
htop

# Disk usage
df -h

# Docker disk usage
docker system df

# Clean up unused Docker resources
docker system prune -a
```

## Additional Services to Consider

Other lightweight services that work well on Pi 3:
- **Portainer** - Docker management UI
- **Uptime Kuma** - Monitoring
- **Mosquitto** - MQTT broker for IoT
- **Node-RED** - Automation flows

## Grafana Dashboard Recommendations

Import these dashboards to visualize Pi metrics:
- **1860** - Node Exporter Full (comprehensive system metrics)
- **10578** - Raspberry Pi Monitoring (temperature and Pi-specific metrics)
- **179** - Docker Container & Host Metrics
- **893** - Docker and System Monitoring

## Service Access URLs

**Pi Services:**
- Homebridge: http://192.168.50.216:8581 or https://homebridge.benlawson.dev
- Pi-hole Admin: http://192.168.50.216/admin or https://pihole.benlawson.dev/admin
- cAdvisor: http://192.168.50.216:8080
- node-exporter: http://192.168.50.216:9100/metrics

**Windows Services:**
- Prometheus: http://localhost:9090 (check /targets for Pi scrape status)
- Grafana: https://grafana.benlawson.dev (view Pi dashboards)
- Homepage: https://homepage.benlawson.dev (shows Pi services)

## Resources

- [Homebridge Documentation](https://github.com/homebridge/homebridge)
- [Pi-hole Documentation](https://docs.pi-hole.net/)
- [Ubuntu on Raspberry Pi](https://ubuntu.com/raspberry-pi)
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboards](https://grafana.com/grafana/dashboards/)
