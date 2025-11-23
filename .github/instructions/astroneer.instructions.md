---
applyTo: "astroneer/**"
---

# Astroneer Dedicated Server Expert Instructions

You are an expert in Astroneer dedicated server management for space exploration multiplayer gameplay.

## Service Overview
Astroneer is a sandbox adventure game set in the 25th century's Intergalactic Age of Discovery. The dedicated server allows hosting persistent multiplayer worlds for cooperative space exploration and base building.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "8777:8777/udp"  # Game port
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/Chicago
  - SERVER_NAME=My Astroneer Server
  - SERVER_PASSWORD=
  - MAX_PLAYERS=8
  - PUBLIC_IP=  # Your public IP
  - OWNER_NAME=YourName
  - OWNER_GUID=  # Steam ID
volumes:
  - ./server-files:/astroneer
  - ./config:/config
restart: unless-stopped
deploy:
  resources:
    limits:
      memory: 4G
    reservations:
      memory: 2G
stop_grace_period: 60s
```

### Critical Files
- `config/Astro/Saved/Config/WindowsServer/AstroServerSettings.ini` - Server config
- `server-files/Astro/Saved/SaveGames/` - World saves

### Default Port
- 8777/UDP - Game connection

## Common Tasks

### First-Time Setup
1. Set OWNER_GUID (your Steam ID64)
2. Start container (downloads server files)
3. Wait for "Server ready" message
4. Connect in-game

### Find Your Steam ID
Get Steam ID64:
1. Visit https://steamid.io/
2. Enter your Steam profile URL
3. Copy "steamID64" value
4. Use in OWNER_GUID environment variable

### Connect to Server
In Astroneer:
1. Multiplayer > Join Game
2. Server List > Favorites
3. Add server via IP:Port (direct connect may not work)
4. Or use Steam Server Browser

### Configure Server Settings
Edit `config/Astro/Saved/Config/WindowsServer/AstroServerSettings.ini`:
```ini
[/Script/Astro.AstroServerSettings]
PublicIP=1.2.3.4
ServerName=My Astroneer Server
OwnerName=YourName
OwnerGuid=76561198012345678
ServerPassword=
MaxServerFramerate=60
MaxServerIdleFramerate=10
bDisableServerTravel=False
DenyUnlistedPlayers=False
VerbosePlayerProperties=True
AutoSaveGameInterval=15
BackupSaveGamesInterval=120
ServerAdvertisedName=My Astroneer Server
ConsolePort=1234
ConsolePassword=admin
```

Restart container after changes.

### Backup World Save
```powershell
docker compose stop
tar -czf "astroneer-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss').tar.gz" server-files/Astro/Saved/SaveGames/
docker compose start
```

### Restore World Save
```powershell
docker compose stop
Remove-Item -Recurse -Force server-files/Astro/Saved/SaveGames/
tar -xzf astroneer-backup-YYYYMMDD-HHMMSS.tar.gz
docker compose start
```

### Reset World (New Save)
```powershell
docker compose stop
Remove-Item -Recurse -Force server-files/Astro/Saved/SaveGames/
docker compose start
```

New world generates on next start.

### Admin Console Access
If ConsolePort and ConsolePassword are configured:
```powershell
telnet localhost 1234
# Enter password when prompted
```

Admin commands available via console.

## Integration Points

### Homepage Dashboard
```yaml
- Astroneer:
    icon: astroneer.png
    href: astroneer://your-ip:8777
    description: Space exploration server
```

### Port Forwarding
Router configuration:
- External port: 8777 UDP
- Internal IP: Server IP
- Internal port: 8777

### Steam Server Browser
Server should appear in Steam:
- View > Servers > Favorites
- Add by IP address

## Troubleshooting

### Server Won't Start
1. Check logs: `docker logs astroneer`
2. Verify OWNER_GUID is set correctly
3. Check disk space
4. Verify port 8777 not in use
5. Check file permissions

### Cannot Connect
1. Verify server is running: `docker ps`
2. Check port forwarding on router
3. Test with local IP first
4. Verify PUBLIC_IP is set correctly
5. Check firewall rules (UDP 8777)
6. Try Steam Server Browser instead of in-game browser

### World Not Loading
1. Check save files exist
2. Verify OWNER_GUID matches save
3. Check for corrupted save files
4. Restore from backup if needed

### Performance Issues/Lag
1. Increase memory allocation
2. Reduce MaxServerFramerate
3. Check network bandwidth
4. Limit concurrent players
5. Monitor: `docker stats astroneer`

### Server Not Visible in Browser
1. Verify PUBLIC_IP is correct
2. Check server is actually running
3. Port forwarding configured correctly
4. Firewall not blocking
5. Try direct connect via IP:Port

## Best Practices

1. **Owner GUID**: Must be set correctly for admin access
2. **Regular Backups**: Automate world backups
3. **Auto-Save**: Keep default 15-minute interval
4. **Player Limit**: 8 players max for stability
5. **Password**: Use password for private servers
6. **Public IP**: Set correctly for server browser listing
7. **Graceful Shutdown**: Allow time for auto-save

## Security Considerations

- **Server Password**: Protect private servers
- **Console Password**: Strong admin console password
- **Port Exposure**: Only expose 8777 UDP
- **Console Port**: Don't expose console port publicly
- **Owner Access**: Only owner has admin privileges
- **Steam Auth**: Required for player authentication

## Advanced Configuration

### Performance Tuning
AstroServerSettings.ini:
```ini
MaxServerFramerate=60
MaxServerIdleFramerate=10
AutoSaveGameInterval=15
BackupSaveGamesInterval=120
```

### Player Management
```ini
DenyUnlistedPlayers=True  # Whitelist mode
VerbosePlayerProperties=True
```

### Server Visibility
```ini
ServerAdvertisedName=My Astroneer Server
bDisableServerTravel=False
```

### Backup Settings
```ini
BackupSaveGamesInterval=120  # Minutes between backups
```

Server creates automatic backups in SaveGames folder.

## System Requirements

### Minimum
- CPU: 2 cores
- RAM: 2GB
- Storage: 5GB
- Network: 10Mbps upload

### Recommended
- CPU: 4 cores
- RAM: 4GB
- Storage: 10GB
- Network: 20Mbps upload

## Gameplay Features

### Cooperative Play
- Up to 8 players
- Shared world and resources
- Persistent base building
- Collaborative exploration

### World Persistence
- Server runs 24/7
- Players can join/leave anytime
- Progress saved automatically
- Backups created periodically

### Planetary System
- Multiple planets to explore
- Resource gathering and trading
- Base construction across planets
- Vehicle and equipment crafting

## Automated Backups

### Backup Script (PowerShell)
```powershell
# astroneer-backup.ps1
$BackupDir = "..\..\Backups\Astroneer"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupFile = "$BackupDir\astroneer-save-$Timestamp.tar.gz"

# Stop server for consistent backup
docker compose -f ..\Docker\astroneer\docker-compose.yml stop
Start-Sleep -Seconds 5

# Backup save files
tar -czf $BackupFile -C ..\Docker\astroneer\server-files\Astro\Saved SaveGames

# Restart server
docker compose -f ..\Docker\astroneer\docker-compose.yml start

# Keep only last 10 backups
Get-ChildItem $BackupDir -Filter "astroneer-save-*.tar.gz" | 
  Sort-Object LastWriteTime -Descending | 
  Select-Object -Skip 10 | 
  Remove-Item

Write-Host "Backup complete: $BackupFile"
```

### Schedule with Task Scheduler
```powershell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File ..\Scripts\astroneer-backup.ps1"
$Trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "Astroneer Backup" -Action $Action -Trigger $Trigger
```

## Monitoring

### Server Logs
```powershell
docker logs -f astroneer
```

### Server Status
```powershell
docker ps | findstr astroneer
```

### Performance
```powershell
docker stats astroneer
```

### Check Save Files
```powershell
Get-ChildItem ..\Docker\astroneer\server-files\Astro\Saved\SaveGames\
```

## Admin Console Commands

If console is enabled and accessible:

### Player Management
```
ListPlayers
KickPlayer <PlayerName>
BanPlayer <SteamID>
```

### Server Management
```
Save
Shutdown
```

### World Management
```
TravelToSolarSystem <SystemName>
```

## Common Issues

### "Connection Timeout"
**Cause**: Port forwarding or firewall issue
**Fix**: 
1. Verify UDP 8777 is forwarded
2. Check firewall allows UDP 8777
3. Test with local IP first

### "Wrong Version"
**Cause**: Client/server version mismatch
**Fix**: Update server or client to match versions

### "Server Full"
**Cause**: MAX_PLAYERS reached
**Fix**: Increase MAX_PLAYERS (max 8 recommended)

### World Corruption
**Cause**: Server crash during save
**Fix**: 
1. Stop server
2. Restore from backup
3. Check disk space and health

## File Size Estimates

- **Server Installation**: ~3-5GB
- **World Save**: 50-200MB (grows with play time)
- **Backup**: Same as save file size
- **Total**: 5-10GB typical

## Update Management

### Manual Update
```powershell
docker compose pull
docker compose up -d
```

Server files update automatically on container restart.

### Version Pinning
```yaml
image: astroneer-server:v1.2.3  # Pin specific version
```

Prevents automatic updates.

## Multiplayer Tips

1. **Voice Chat**: Use Discord or Steam Voice (game has no built-in voice)
2. **Coordination**: Plan base layout before building
3. **Resource Sharing**: Use storage platforms for sharing
4. **Exploration**: Split up to cover more ground
5. **Backup Before Major Changes**: Save manually before risky activities

This cooperative space exploration server provides persistent multiplayer worlds for base building and planetary exploration in the Docker gaming server stack.
