---
applyTo: "pi/cloudflare-tunnel/**"
---

# Cloudflare Tunnel Service Expert Instructions

You are an expert in Cloudflare Tunnel (cloudflared) configuration and secure remote access.

## Service Overview
Cloudflare Tunnel creates a secure, outbound-only connection between your services and Cloudflare's network, eliminating the need for public IP addresses, port forwarding, or VPN. This tunnel specifically provides secure external access to the Homebridge web interface.

## Technical Configuration

### Network Requirements
- **No inbound ports required** - All connections are outbound to Cloudflare
- Connects to Homebridge via Docker bridge network
- Homebridge remains on `host` network for HomeKit/mDNS functionality
- Tunnel container connects to shared `homebridge-net` bridge network

### Docker Compose Patterns
```yaml
services:
  cloudflare-tunnel:
    image: cloudflare/cloudflared:latest
    command: tunnel run
    environment:
      - TUNNEL_TOKEN=${TUNNEL_TOKEN}
    networks:
      - homebridge-net
    restart: unless-stopped
```

### Network Architecture
```
Internet → Cloudflare Edge → Tunnel (host network) → Homebridge (host network)
```

Since both the tunnel and Homebridge run on the same Pi using host networking, the tunnel can connect to Homebridge via localhost:8581.

## Setup Process

### 1. Create Tunnel in Cloudflare Dashboard
1. Log in to [Cloudflare Zero Trust](https://one.dash.cloudflare.com/)
2. Navigate to **Networks** > **Tunnels**
3. Click **Create a tunnel**
4. Choose **Cloudflared** connector type
5. Name your tunnel (e.g., "homebridge")
6. Click **Save tunnel**

### 2. Configure Public Hostname
1. In the tunnel configuration, go to **Public Hostname** tab
2. Click **Add a public hostname**
3. Configure:
   - **Subdomain**: `homebridge` (or your preference)
   - **Domain**: Select your domain (e.g., `benlawson.dev`)
   - **Service Type**: `HTTP`
   - **URL**: `localhost:8581` (since tunnel runs on host network with Homebridge)
4. Under **Additional application settings**:
   - Enable **No TLS Verify** if using self-signed certs
   - Optional: Configure **Cloudflare Access** for authentication
5. Click **Save hostname**

### 3. Get Tunnel Token
1. In the tunnel dashboard, click **Configure**
2. Select **Docker** from the connector options
3. Copy the token from the command:
   ```bash
   docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token YOUR_TOKEN_HERE
   ```
4. Copy only the token value (long alphanumeric string)

### 4. Deploy the Tunnel
```bash
cd /home/rubiss/docker/pi/cloudflare-tunnel
cp .env.example .env
# Edit .env and paste your tunnel token
nano .env

# Start the tunnel
docker compose up -d

# Verify it's running
docker logs cloudflare-tunnel-homebridge
```

### 5. Network Configuration
Both services run on the same Pi using host networking:
```yaml
# Tunnel: pi/cloudflare-tunnel/docker-compose.yml
services:
  cloudflare-tunnel:
    network_mode: host  # Shares Pi's network
    
# Homebridge: pi/homebridge/docker-compose.yml
services:
  homebridge:
    network_mode: host  # Required for HomeKit mDNS
```

Since both are on host network, tunnel connects to Homebridge via `localhost:8581`.

## Common Tasks

### View Tunnel Logs
```bash
docker logs cloudflare-tunnel-homebridge -f
```

### Check Tunnel Status
- View in Cloudflare Dashboard under Networks > Tunnels
- Should show "Healthy" status with active connections

### Restart Tunnel
```bash
docker restart cloudflare-tunnel-homebridge
```

### Update Tunnel Token
```bash
cd /home/rubiss/docker/pi/cloudflare-tunnel
nano .env  # Update TUNNEL_TOKEN
docker compose up -d  # Restart with new token
```

## Troubleshooting

### Tunnel Not Connecting
1. **Check token validity**: Ensure token is correct and not expired
2. **Verify DNS**: Confirm subdomain resolves to Cloudflare IPs
3. **Check logs**: `docker logs cloudflare-tunnel-homebridge`
4. **Network connectivity**: Ensure container can reach Cloudflare edge

### Cannot Access Homebridge
1. **Verify service URL**: Should be `localhost:8581` (both services on host network)
2. **Check Homebridge is running**: `docker ps | grep homebridge`
3. **Test local access**: `curl http://localhost:8581` or `curl http://192.168.50.216:8581`
4. **Review tunnel config**: Ensure public hostname is saved correctly

### SSL/TLS Errors
- Enable **No TLS Verify** in tunnel config if Homebridge uses self-signed cert
- Or configure Homebridge to use valid SSL certificate

### Tunnel Shows Offline
1. Restart the container
2. Regenerate tunnel token if persistent
3. Check Cloudflare service status
4. Verify no firewall blocking outbound connections

## Security Best Practices

1. **Use Cloudflare Access**: Add authentication layer before Homebridge
2. **Enable Audit Logs**: Monitor who accesses your tunnel
3. **Rotate Tokens**: Periodically regenerate tunnel tokens
4. **Limit Access**: Use Cloudflare Access policies to restrict by email/IP
5. **Monitor Usage**: Review tunnel analytics for unusual traffic

## Integration with Homebridge

### Why This Setup?
- **Homebridge needs host network** for HomeKit mDNS/Bonjour discovery
- **Tunnel also uses host network** for simplicity and direct localhost access
- **Solution**: Both run on Pi (192.168.50.216) using host networking, tunnel connects via localhost:8581

### Why Not Bridge Network?
Host networking is simpler since both services need to be on the Pi:
```yaml
# Bridge network alternative - more complex, no benefit here
services:
  cloudflare-tunnel:
    networks:
      - homebridge-net
  homebridge:
    network_mode: host  # Still needs host for HomeKit
    
networks:
  homebridge-net:
    external: true
```

The tunnel would need to connect to `192.168.50.216:8581` instead of `localhost:8581`.

## Cloudflare Access (Optional)

### Add Authentication Layer
1. In Cloudflare Zero Trust, go to **Access** > **Applications**
2. Click **Add an application** > **Self-hosted**
3. Configure:
   - **Application name**: Homebridge
   - **Session duration**: 24 hours
   - **Application domain**: `homebridge.benlawson.dev`
4. Add Access Policy:
   - **Policy name**: Allow specific users
   - **Action**: Allow
   - **Include**: Emails (`your@email.com`)
5. Save and deploy

Now accessing `homebridge.benlawson.dev` requires Cloudflare authentication.

## Monitoring

### Tunnel Health
- Check Cloudflare Dashboard for uptime/downtime events
- Set up alerts for tunnel disconnections
- Monitor bandwidth usage

### Homebridge Availability
- Use Uptime Kuma or similar to monitor `https://homebridge.benlawson.dev`
- Set up Homepage widget to show tunnel status

## Advanced Configuration

### Config File Method (Alternative to Token)
Instead of using `TUNNEL_TOKEN`, you can use a config file:

1. Create `config.yml`:
```yaml
tunnel: your-tunnel-id
credentials-file: /etc/cloudflared/credentials.json
ingress:
  - hostname: homebridge.benlawson.dev
    service: http://localhost:8581
  - service: http_status:404
```

2. Update docker-compose.yml:
```yaml
services:
  cloudflare-tunnel:
    command: tunnel --config /etc/cloudflared/config.yml run
    volumes:
      - ./config.yml:/etc/cloudflared/config.yml:ro
      - ./credentials.json:/etc/cloudflared/credentials.json:ro
```

### Multiple Services Through One Tunnel
Configure multiple hostnames in Cloudflare Dashboard (all services on Pi at 192.168.50.216):
- `homebridge.benlawson.dev` → `http://localhost:8581` (Homebridge)
- `pihole.benlawson.dev` → `http://localhost:80` (Pi-hole if on same Pi)
- Other services on Windows host (192.168.50.40) would need separate tunnel or use Pi IP

## Backup & Recovery

### Backup Tunnel Token
```bash
# Copy .env file to secure location
cp .env .env.backup
```

### Recreate Tunnel
If tunnel is deleted from Cloudflare:
1. Create new tunnel in dashboard
2. Update `.env` with new token
3. Restart container: `docker compose up -d`

## References
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Cloudflare Access Documentation](https://developers.cloudflare.com/cloudflare-one/applications/)
- [Homebridge on host network](https://github.com/homebridge/docker-homebridge#network-modes)
