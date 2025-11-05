---
applyTo: "valheim/**"
---

# Valheim Server Expert Instructions

You are an expert in Valheim dedicated server configuration and management.

## Service Overview
Valheim is a survival and sandbox Viking-themed game. This Docker configuration runs a dedicated Valheim server for multiplayer gameplay with persistent world data and automatic updates.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "2456:2456/udp"  # Game port
  - "2457:2457/udp"  # Game port
volumes:
  - ./config:/config
  - ./data:/opt/valheim
environment:
  - SERVER_NAME=${SERVER_NAME}
  - WORLD_NAME=${WORLD_NAME}
  - SERVER_PASS=${SERVER_PASS}
  - SERVER_PUBLIC=false
  - UPDATE_CRON="0 5 * * *"  # Update at 5 AM daily
  - TZ=America/New_York
restart: unless-stopped
stop_grace_period: 2m
```

### Critical Files
- `config/` - Server configuration
- `data/worlds/` - World save files
- `valheim.env` - Environment variables (passwords, etc.)

### Default Ports
- 2456-2457/UDP - Game server

## Common Tasks

### First-Time Setup
1. Set environment variables in `valheim.env`:
```bash
SERVER_NAME=My Valheim Server
WORLD_NAME=Dedicated
SERVER_PASS=YourSecurePassword
```

2. Start server:
```powershell
docker compose up -d
```

3. Wait for initial download (~1GB)
4. Check logs: `docker logs valheim -f`
5. Connect in-game: Server list or IP:2456

### Connect to Server
In Valheim:
1. Play > Join Game
2. Community tab or Manual IP
3. Enter: `your-public-ip:2456`
4. Password: Value of `SERVER_PASS`

### Backup World
```powershell
docker compose stop
tar -czf valheim-world-$(Get-Date -Format "yyyyMMdd").tar.gz data/worlds/
docker compose start
```

### View Server Logs
```powershell
docker logs valheim -f
```

### Update Server
Automatic via `UPDATE_CRON`, or manual:
```powershell
docker compose pull
docker compose up -d
```

### Change Server Settings
Edit `valheim.env`, then:
```powershell
docker compose up -d
```

## Integration Points

### Port Forwarding
Router must forward:
- 2456/UDP
- 2457/UDP
- To server's local IP

### Homepage Dashboard
```yaml
- Valheim Server:
    icon: valheim.png
    href: steam://connect/your-ip:2456
    description: Viking survival server
```

### Monitoring
Check if server is up:
```powershell
# Check container is running
docker ps | findstr valheim

# Check logs for "Game server connected"
docker logs valheim --tail 50
```

## Troubleshooting

### Cannot Connect to Server
1. Verify container is running: `docker ps`
2. Check ports 2456-2457 UDP are forwarded
3. Test connectivity: Use server query tools
4. Verify password is correct
5. Check firewall allows UDP traffic

### World Not Saving
1. Check disk space: `df -h`
2. Verify volume mounts are correct
3. Review logs for save errors
4. Ensure proper shutdown (stop_grace_period)

### Server Crashes/Restarts
1. Check RAM usage (Valheim needs 2-4GB)
2. Review crash logs in `config/logs/`
3. Verify Docker has sufficient resources
4. Check for Valheim updates

### Players Experiencing Lag
1. Check server CPU/RAM usage
2. Verify network bandwidth
3. Reduce world complexity (remove structures)
4. Check player count vs. server specs

## Best Practices

1. **Regular Backups**: Backup worlds before updates
2. **Graceful Shutdown**: Use stop_grace_period for saving
3. **Password Protection**: Always set strong SERVER_PASS
4. **Auto-Updates**: Enable UPDATE_CRON for patches
5. **Resource Monitoring**: Watch CPU/RAM usage
6. **World Backups**: Keep multiple world save copies
7. **Server Restarts**: Weekly restart for performance

## Security Considerations

- **Password**: Set strong `SERVER_PASS`
- **Public Listing**: Keep `SERVER_PUBLIC=false` for private servers
- **Port Exposure**: Only 2456-2457, not full host
- **Whitelist**: Consider IP whitelist for trusted players
- **Firewall**: Restrict UDP ports to game traffic only

## Advanced Configuration

### Environment Variables
```bash
# Server identity
SERVER_NAME=My Valheim Server
WORLD_NAME=Dedicated
SERVER_PASS=StrongPassword123

# Visibility
SERVER_PUBLIC=false  # Don't list publicly

# Updates
UPDATE_CRON="0 5 * * *"  # Daily at 5 AM
RESTART_CRON="0 6 * * *"  # Restart at 6 AM

# Performance
TZ=America/New_York
PUID=1000
PGID=1000
```

### Server Modifiers
Some servers support:
- Player damage multipliers
- Resource respawn rates
- Raid difficulty
- Death penalties

Check server mod documentation.

### Mods (BepInEx)
Install mods:
1. Download BepInEx pack
2. Extract to `config/BepInEx/`
3. Add mod DLLs to `config/BepInEx/plugins/`
4. Restart server

Popular mods:
- ValheimPlus (QoL improvements)
- EpicLoot
- Custom textures

### Backup Automation
```powershell
# backup-valheim.ps1
$date = Get-Date -Format "yyyyMMdd-HHmmss"
docker compose stop valheim
tar -czf "valheim-backup-$date.tar.gz" data/worlds/
docker compose start valheim

# Keep last 7 days
Get-ChildItem . -Filter "valheim-backup-*.tar.gz" | 
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | 
  Remove-Item
```

Schedule with Task Scheduler.

## Performance Tuning

### For Large Worlds
Increase Docker resources:
```yaml
deploy:
  resources:
    limits:
      memory: 8G
      cpus: '4'
```

### Reduce Save Frequency
Edit server config (if available):
- Reduce auto-save interval
- Manual saves only

### Optimize World
- Remove unnecessary structures
- Clear old items
- Prune world data

## Monitoring

### Server Status
```powershell
# Check if running
docker ps | findstr valheim

# Check logs for players
docker logs valheim | findstr "Got character"
```

### Player Count
Check logs for connections:
```powershell
docker logs valheim | findstr "Got connection"
```

### Resource Usage
```powershell
docker stats valheim
```

## Common Errors

### "Failed to connect"
- Port forwarding not configured
- Firewall blocking UDP
- Server still starting
- Wrong password

### "Version mismatch"
- Client/server versions differ
- Update server: `docker compose pull && docker compose up -d`
- Update game client

### World corruption
- Hard server crash
- Restore from backup
- May need to regenerate world

## Game Updates

### Automatic Updates
Configured via `UPDATE_CRON`:
```bash
UPDATE_CRON="0 5 * * *"  # Daily at 5 AM
```

Server checks for updates and applies automatically.

### Manual Update
```powershell
docker compose pull
docker compose up -d
```

### Rollback Version
If update breaks server:
```yaml
image: lloesche/valheim-server:1.2.3  # Pin specific version
```

## World Management

### Multiple Worlds
Create different world configs:
```yaml
# docker-compose-world2.yml
environment:
  - WORLD_NAME=SecondWorld
```

Run: `docker compose -f docker-compose-world2.yml up -d`

### Transfer World
1. Backup world from `data/worlds/`
2. Copy `.db` and `.fwl` files
3. Place in new server's `data/worlds/`
4. Set `WORLD_NAME` to match filename
5. Start server

### Reset World
```powershell
docker compose stop
Remove-Item data/worlds/* -Recurse -Force
docker compose start
```

Server generates new world.

## Community Resources

- Valheim Discord
- r/valheim subreddit
- Valheim Wiki
- Dedicated server guides
- Mod communities (Nexus Mods, Thunderstore)

This dedicated server setup provides a persistent Valheim world for multiplayer Viking adventures with automated maintenance and backups.
