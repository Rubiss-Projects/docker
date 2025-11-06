# Windows Host Changes - Summary

This document summarizes all changes made to your Windows host Docker configuration to support the Raspberry Pi integration.

## Files Modified

### 1. Prometheus Configuration
**File:** `E:\Docker\prometheus\config\prometheus.yml`

**Added scrape jobs for Pi:**
```yaml
  # Raspberry Pi - Container metrics
  - job_name: 'cadvisor-pi'
    scrape_interval: 30s
    static_configs:
      - targets: ['192.168.50.216:8080']
        labels:
          instance: 'raspberry-pi'
          host: 'pi3'

  # Raspberry Pi - System metrics
  - job_name: 'node-exporter-pi'
    scrape_interval: 15s
    static_configs:
      - targets: ['192.168.50.216:9100']
        labels:
          instance: 'raspberry-pi'
          host: 'pi3'
```

**Action Required:** Restart Prometheus after commit
```powershell
cd E:\Docker\prometheus
docker compose restart
```

### 2. Homepage Dashboard
**File:** `E:\Docker\homepage\config\services.yaml`

**Added new "Raspberry Pi" section:**
- Homebridge (Pi) widget
- Pi-hole widget
- Pi System Monitor link (cAdvisor)

**Note:** Pi-hole API key needs to be updated once Pi-hole is deployed.

**Action Required:** None (Homepage auto-reloads config)

## Services Ready for Pi Integration

### Monitoring Stack (Prometheus & Grafana)
✅ Prometheus configured to scrape Pi metrics  
✅ Ready for Grafana dashboard imports  
✅ Metrics will show alongside Windows metrics  

**Recommended Grafana Dashboards:**
- Import ID 1860: Node Exporter Full
- Import ID 10578: Raspberry Pi Monitoring

### Homepage Dashboard
✅ Pi services section added  
✅ Widget configurations pre-set  
⚠️ Pi-hole API key needs manual update after deployment  

### Nginx Proxy Manager (Manual Setup Required)
Create proxy hosts for:
- `homebridge.benlawson.dev` → `http://192.168.50.216:8581`
- `pihole.benlawson.dev` → `http://192.168.50.216:80`

**Steps:**
1. Open NPM admin panel
2. Add Proxy Host for Homebridge:
   - Domain: homebridge.benlawson.dev
   - Forward to: 192.168.50.216:8581
   - Enable SSL, Websockets
3. Add Proxy Host for Pi-hole:
   - Domain: pihole.benlawson.dev
   - Forward to: 192.168.50.216:80
   - Enable SSL, add custom location `/admin`

## Verification Steps

### After Prometheus Restart:
1. Open http://localhost:9090
2. Go to Status → Targets
3. Look for `cadvisor-pi` and `node-exporter-pi`
4. Initially will show DOWN (Pi not deployed yet)
5. Will turn UP once Pi services are running

### After Pi Deployment:
1. Check Prometheus targets: Both Pi targets should be UP
2. Check Homepage: Pi services should show status
3. Test queries in Prometheus:
   ```promql
   node_hwmon_temp_celsius{host="pi3"}
   node_memory_MemAvailable_bytes{host="pi3"}
   ```

### After NPM Configuration:
1. Test Homebridge: https://homebridge.benlawson.dev
2. Test Pi-hole: https://pihole.benlawson.dev/admin

## What's Pre-Configured

✅ **IP Address:** All configs use 192.168.50.216  
✅ **Prometheus:** Ready to scrape Pi metrics  
✅ **Homepage:** Ready to display Pi widgets  
✅ **Labels:** Pi metrics tagged with `host="pi3"` for filtering  

## What Needs Manual Configuration

⚠️ **Nginx Proxy Manager:** Create proxy hosts manually  
⚠️ **Pi-hole API Key:** Update in Homepage after Pi-hole deployment  
⚠️ **Grafana Dashboards:** Import after Pi deployment  

## Network Requirements

- Pi must have static IP: **192.168.50.216**
- Windows host must be able to reach Pi on ports: 8080, 9100, 8581, 80
- Both must be on same subnet (192.168.50.0/24)

## Next Steps

1. ✅ Commit these changes to git
2. ✅ Push to GitHub
3. 🔄 Follow HUMAN-SETUP-GUIDE.md to set up Pi
4. 🔄 Use AI-SETUP-INSTRUCTIONS.md for automated deployment
5. ⚙️ Update Pi-hole API key in Homepage
6. ⚙️ Configure NPM proxy hosts
7. ⚙️ Import Grafana dashboards
8. ✅ Verify all integrations working

## Rollback Instructions

If you need to revert changes:

**Prometheus:**
```powershell
cd E:\Docker\prometheus\config
git checkout HEAD -- prometheus.yml
cd E:\Docker\prometheus
docker compose restart
```

**Homepage:**
```powershell
cd E:\Docker\homepage\config
git checkout HEAD -- services.yaml
```

## Questions & Troubleshooting

**Q: Why 192.168.50.216?**  
A: Static IP assigned for the Raspberry Pi to ensure consistent access for monitoring and proxy configuration.

**Q: Can I change the IP?**  
A: Yes, but you'll need to update: Prometheus config, Homepage config, Pi .env files, NPM proxy hosts.

**Q: Why not use hostname instead of IP?**  
A: Prometheus requires reliable resolution. Static IP is more reliable than mDNS (.local) across Docker networks.

**Q: Do I need to configure anything else on Windows?**  
A: Just Prometheus restart (after commit) and NPM proxy hosts (manual). Everything else is ready.
