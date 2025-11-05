# AI Agent Setup Instructions - Raspberry Pi 3

**Context:** The human has completed initial Pi setup (Ubuntu Server installed, Git configured, VS Code tunnel connected, repo cloned). The Pi is accessible at IP `192.168.50.41`. You are now responsible for installing Docker and deploying all configured services.

**Your Mission:** Automate the complete Docker service deployment on this Raspberry Pi 3.

## System Information

- **Device:** Raspberry Pi 3
- **OS:** Ubuntu Server 24.04.3 LTS (64-bit ARM)
- **RAM:** 1GB (resource-constrained)
- **IP Address:** 192.168.50.41 (static)
- **Repository:** Already cloned at `~/docker/pi`
- **User:** `pi` (or as configured)

## Services to Deploy

1. **Homebridge** - HomeKit integration (port 8581)
2. **Pi-hole** - DNS ad blocking (port 80)
3. **Watchtower** - Auto-update containers (background)
4. **cAdvisor** - Container metrics for Prometheus (port 8080)
5. **node-exporter** - System metrics for Prometheus (port 9100)

## Pre-Flight Checklist

Before starting, verify:

```bash
# Check you're in the right directory
pwd
# Should output: /home/pi/docker/pi

# Check Ubuntu version
lsb_release -a
# Should show: Ubuntu 24.04

# Check network connectivity
ping -c 3 google.com

# Verify static IP
ip addr show | grep "192.168.50.41"
```

## Step 1: Install Docker

```bash
# Update package lists
sudo apt update

# Install Docker and Docker Compose
sudo apt install -y docker.io docker-compose

# Verify installation
docker --version
docker compose version

# Add current user to docker group (no sudo needed for docker commands)
sudo usermod -aG docker $USER

# Apply group changes (IMPORTANT)
newgrp docker

# Test Docker without sudo
docker ps
# Should work without errors (even if empty)
```

## Step 2: Prepare Environment Files

```bash
cd ~/docker/pi

# Copy all .env.example files to .env
for dir in homebridge pi-hole watchtower cadvisor node-exporter; do
    if [ -f "$dir/.env.example" ]; then
        cp "$dir/.env.example" "$dir/.env"
        echo "✓ Created $dir/.env"
    fi
done

# Verify .env files were created
find . -name ".env" -type f
```

**Note:** The .env files are pre-configured with correct IP (192.168.50.41). Only Pi-hole WEBPASSWORD needs to be changed by the user later.

## Step 3: Deploy Services in Order

### 3a. Deploy Homebridge

```bash
cd ~/docker/pi/homebridge
docker compose up -d

# Wait for container to start
sleep 10

# Verify running
docker compose ps
docker compose logs --tail 20

# Look for Homebridge PIN in logs (user will need this)
docker compose logs | grep -i "pin"
```

**Expected:** Container named `homebridge` running, port 8581 exposed.

### 3b. Deploy Pi-hole

```bash
cd ~/docker/pi/pi-hole
docker compose up -d

# Wait for initialization
sleep 15

# Verify running
docker compose ps
docker compose logs --tail 20
```

**Expected:** Container named `pihole` running, ports 53, 67, 80 exposed.

### 3c. Deploy Watchtower

```bash
cd ~/docker/pi/watchtower
docker compose up -d

# Verify running
docker compose ps
docker compose logs --tail 10
```

**Expected:** Container named `watchtower` running in background.

### 3d. Deploy cAdvisor (Monitoring)

```bash
cd ~/docker/pi/cadvisor
docker compose up -d

# Wait for startup
sleep 10

# Verify running
docker compose ps

# Test metrics endpoint
curl -s http://localhost:8080/metrics | head -20
```

**Expected:** Container named `cadvisor` running, port 8080 exposed, metrics available.

### 3e. Deploy node-exporter (Monitoring)

```bash
cd ~/docker/pi/node-exporter
docker compose up -d

# Wait for startup
sleep 5

# Verify running
docker compose ps

# Test metrics endpoint (note: uses host networking, so no container port mapping)
curl -s http://localhost:9100/metrics | head -20
```

**Expected:** Container named `node-exporter` running, metrics available on port 9100.

## Step 4: Verification

### 4a. Check All Containers Running

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Expected output:**
```
NAMES           STATUS              PORTS
homebridge      Up X minutes        0.0.0.0:8581->8581/tcp
pihole          Up X minutes        0.0.0.0:53->53/tcp, 0.0.0.0:80->80/tcp, ...
watchtower      Up X minutes        
cadvisor        Up X minutes        0.0.0.0:8080->8080/tcp
node-exporter   Up X minutes        
```

All 5 containers should show "Up" status.

### 4b. Check Resource Usage

```bash
docker stats --no-stream
```

**Expected:** Total memory usage should be <400MB (Pi has 1GB RAM).

### 4c. Test Service Endpoints

```bash
# Homebridge web UI
curl -I http://localhost:8581

# Pi-hole web UI
curl -I http://localhost/admin

# cAdvisor metrics
curl -s http://localhost:8080/metrics | wc -l

# node-exporter metrics
curl -s http://localhost:9100/metrics | wc -l
```

All should return successful responses (200 OK or metrics data).

### 4d. Check System Temperature

```bash
# Check if Pi is running hot
vcgencmd measure_temp

# View node-exporter temperature metrics
curl -s http://localhost:9100/metrics | grep "node_hwmon_temp_celsius"
```

**Expected:** Temperature <60°C (warm but safe). Over 70°C is concerning, over 80°C causes throttling.

## Step 5: Final Configuration Notes

### For the Human User:

**Homebridge:**
- Access: http://192.168.50.41:8581
- Also proxied: https://homebridge.benlawson.dev
- PIN code is in logs: `docker logs homebridge | grep PIN`
- Default credentials: admin / admin (change on first login)

**Pi-hole:**
- Access: http://192.168.50.41/admin
- Also proxied: https://pihole.benlawson.dev/admin
- Password is set in `.env` file (default: changeme123 - MUST CHANGE)
- To get API key for Homepage: `docker exec pihole cat /etc/pihole/setupVars.conf | grep WEBPASSWORD`

**Monitoring:**
- cAdvisor UI: http://192.168.50.41:8080
- Metrics are already being scraped by Prometheus on Windows host
- Check Grafana dashboards on Windows for Pi stats

**Watchtower:**
- Runs in background, no UI
- Automatically updates containers daily at 4 AM
- Check logs: `docker logs watchtower`

## Step 6: Enable Auto-Start on Reboot

```bash
# Ensure all containers restart automatically
cd ~/docker/pi

for dir in homebridge pi-hole watchtower cadvisor node-exporter; do
    cd ~/docker/pi/$dir
    docker compose up -d --no-recreate
    echo "✓ Updated $dir"
done
```

All compose files already have `restart: unless-stopped`, so containers will auto-start on Pi reboot.

## Step 7: Create Start/Stop Helper Script

```bash
cat > ~/docker/pi/manage-services.sh << 'EOF'
#!/bin/bash
# Manage all Pi services

ACTION=$1
SERVICES=("homebridge" "pi-hole" "watchtower" "cadvisor" "node-exporter")

if [ "$ACTION" != "start" ] && [ "$ACTION" != "stop" ] && [ "$ACTION" != "restart" ] && [ "$ACTION" != "status" ]; then
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
fi

for service in "${SERVICES[@]}"; do
    echo "[$service] $ACTION..."
    cd ~/docker/pi/$service
    
    case $ACTION in
        start)
            docker compose up -d
            ;;
        stop)
            docker compose down
            ;;
        restart)
            docker compose restart
            ;;
        status)
            docker compose ps
            ;;
    esac
done

if [ "$ACTION" == "status" ]; then
    echo ""
    echo "=== Overall Resource Usage ==="
    docker stats --no-stream
fi
EOF

chmod +x ~/docker/pi/manage-services.sh

echo "✓ Created management script: ~/docker/pi/manage-services.sh"
```

**Usage:**
```bash
~/docker/pi/manage-services.sh start    # Start all
~/docker/pi/manage-services.sh stop     # Stop all
~/docker/pi/manage-services.sh restart  # Restart all
~/docker/pi/manage-services.sh status   # Check status
```

## Step 8: Final Report

Generate a summary report:

```bash
cat << 'EOF'

================================================================
      RASPBERRY PI DOCKER SETUP - COMPLETION REPORT
================================================================

SYSTEM INFORMATION:
-------------------
EOF

echo "Hostname:       $(hostname)"
echo "IP Address:     $(hostname -I | awk '{print $1}')"
echo "OS Version:     $(lsb_release -ds)"
echo "Kernel:         $(uname -r)"
echo "Uptime:         $(uptime -p)"
echo "Temperature:    $(vcgencmd measure_temp)"
echo ""

cat << 'EOF'
DOCKER INFORMATION:
-------------------
EOF

echo "Docker Version: $(docker --version)"
echo "Compose Version: $(docker compose version)"
echo ""

cat << 'EOF'
DEPLOYED SERVICES:
------------------
EOF

docker ps --format "{{.Names}}: {{.Status}}"
echo ""

cat << 'EOF'
RESOURCE USAGE:
---------------
EOF

docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
echo ""

cat << 'EOF'
SERVICE ENDPOINTS:
------------------
EOF

PI_IP=$(hostname -I | awk '{print $1}')
echo "Homebridge:      http://$PI_IP:8581"
echo "                 https://homebridge.benlawson.dev"
echo ""
echo "Pi-hole Admin:   http://$PI_IP/admin"
echo "                 https://pihole.benlawson.dev/admin"
echo ""
echo "cAdvisor:        http://$PI_IP:8080"
echo "node-exporter:   http://$PI_IP:9100/metrics"
echo ""

cat << 'EOF'
NEXT STEPS FOR USER:
--------------------
1. Change Pi-hole admin password:
   - Edit ~/docker/pi/pi-hole/.env
   - Change WEBPASSWORD value
   - Run: cd ~/docker/pi/pi-hole && docker compose up -d --force-recreate

2. Get Homebridge PIN for HomeKit pairing:
   docker logs homebridge | grep -A 5 "Setup Payload"

3. Get Pi-hole API key for Homepage dashboard:
   docker exec pihole cat /etc/pihole/setupVars.conf | grep WEBPASSWORD

4. Check Prometheus on Windows is scraping Pi metrics:
   http://localhost:9090/targets
   (Look for cadvisor-pi and node-exporter-pi showing UP)

5. Import Grafana dashboards for Pi monitoring:
   - Dashboard 1860: Node Exporter Full
   - Dashboard 10578: Raspberry Pi Monitoring

6. Configure Pi-hole as DNS server:
   - Set router DNS to 192.168.50.41
   - Or configure per-device DNS settings

MONITORING:
-----------
✓ Prometheus on Windows is configured to scrape Pi metrics
✓ Grafana dashboards will show Pi stats alongside Windows stats
✓ Homepage dashboard has been updated with Pi services
✓ cAdvisor provides container-level metrics
✓ node-exporter provides system-level metrics

MAINTENANCE:
------------
- Management script: ~/docker/pi/manage-services.sh
- Update all containers: docker compose pull && docker compose up -d
- Watchtower auto-updates daily at 4 AM
- Check logs: docker compose logs -f [service-name]

================================================================
                    SETUP COMPLETE! 🎉
================================================================

EOF
```

## Troubleshooting

### If any container fails to start:

```bash
# Check logs for errors
docker compose logs [service-name]

# Check disk space
df -h

# Check memory
free -h

# Restart container
docker compose restart [service-name]

# Force recreate
docker compose up -d --force-recreate [service-name]
```

### If metrics aren't showing in Prometheus:

```bash
# Verify metrics endpoints are accessible
curl http://localhost:8080/metrics  # cAdvisor
curl http://localhost:9100/metrics  # node-exporter

# Check if ports are listening
sudo netstat -tulpn | grep -E '8080|9100'

# Verify from Windows host
# On Windows PowerShell:
Test-NetConnection 192.168.50.41 -Port 8080
Test-NetConnection 192.168.50.41 -Port 9100
```

### If Pi is running hot (>70°C):

```bash
# Check current temperature
vcgencmd measure_temp

# Check if throttling
vcgencmd get_throttled
# 0x0 = no throttling, anything else = throttled

# Check resource usage
htop
docker stats

# Consider:
# 1. Ensure good ventilation
# 2. Add heatsinks or fan
# 3. Reduce number of running services
```

## Success Criteria

✅ All 5 containers running (homebridge, pihole, watchtower, cadvisor, node-exporter)  
✅ No errors in logs  
✅ All endpoints accessible (8581, 80, 8080, 9100)  
✅ Memory usage <500MB total  
✅ Temperature <70°C  
✅ Services auto-start on reboot  
✅ Management script created and functional  

## Completion

Once all services are verified running and healthy, your task is complete. The user can now:
- Access Homebridge and Pi-hole web interfaces
- View Pi metrics in Grafana on Windows host
- Monitor all containers via cAdvisor
- Rely on Watchtower for automatic updates

Report the completion summary generated in Step 8 to the user.
