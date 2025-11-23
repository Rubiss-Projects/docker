---
applyTo: "palworld/**"
---

# Palworld Server Expert Instructions

You are an expert in Palworld dedicated server management.

## Service Overview
Palworld is a multiplayer survival game with creature collecting mechanics. The dedicated server allows hosting private multiplayer sessions with custom configuration.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "8211:8211/udp"  # Game port
  - "27015:27015/udp"  # Query port (optional)
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/Chicago
  - PORT=8211
  - PLAYERS=32
  - MULTITHREADING=true
  - COMMUNITY=false  # Public server
  - PUBLIC_IP=  # Your public IP
  - PUBLIC_PORT=8211
  - SERVER_NAME=My Palworld Server
  - SERVER_PASSWORD=secret
  - ADMIN_PASSWORD=admin_secret
  - UPDATE_ON_BOOT=true
  - RCON_ENABLED=true
  - RCON_PORT=25575
  - REGION=  # Optional region lock
volumes:
  - ./data:/palworld
restart: unless-stopped
```

### Critical Files
- `data/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini` - Server settings
- `data/Pal/Saved/SaveGames/` - World saves
- `data/steamcmd/` - SteamCMD installation

### Default Ports
- 8211/UDP - Game server
- 27015/UDP - Query port (optional)
- 25575/TCP - RCON (if enabled)

## Common Tasks

### First-Time Setup
1. Configure environment variables
2. Start container (downloads game ~8GB)
3. Wait for "Setting breakpad minidump AppID" message
4. Connect in-game: IP:8211

### Connect to Server
In Palworld:
1. Multiplayer
2. Join Multiplayer Game (Dedicated Server)
3. Enter server IP: `server-ip:8211`
4. Enter password if set

### Configure Server Settings
Edit `data/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini`:
```ini
[/Script/Pal.PalGameWorldSettings]
OptionSettings=(Difficulty=None,DayTimeSpeedRate=1.000000,NightTimeSpeedRate=1.000000,ExpRate=1.000000,PalCaptureRate=1.000000,PalSpawnNumRate=1.000000,PalDamageRateAttack=1.000000,PalDamageRateDefense=1.000000,PlayerDamageRateAttack=1.000000,PlayerDamageRateDefense=1.000000,PlayerStomachDecreaceRate=1.000000,PlayerStaminaDecreaceRate=1.000000,PlayerAutoHPRegeneRate=1.000000,PlayerAutoHpRegeneRateInSleep=1.000000,PalStomachDecreaceRate=1.000000,PalStaminaDecreaceRate=1.000000,PalAutoHPRegeneRate=1.000000,PalAutoHpRegeneRateInSleep=1.000000,BuildObjectDamageRate=1.000000,BuildObjectDeteriorationDamageRate=1.000000,CollectionDropRate=1.000000,CollectionObjectHpRate=1.000000,CollectionObjectRespawnSpeedRate=1.000000,EnemyDropItemRate=1.000000,DeathPenalty=All,bEnablePlayerToPlayerDamage=False,bEnableFriendlyFire=False,bEnableInvaderEnemy=True,bActiveUNKO=False,bEnableAimAssistPad=True,bEnableAimAssistKeyboard=False,DropItemMaxNum=3000,DropItemMaxNum_UNKO=100,BaseCampMaxNum=128,BaseCampWorkerMaxNum=15,DropItemAliveMaxHours=1.000000,bAutoResetGuildNoOnlinePlayers=False,AutoResetGuildTimeNoOnlinePlayers=72.000000,GuildPlayerMaxNum=20,PalEggDefaultHatchingTime=72.000000,WorkSpeedRate=1.000000,bIsMultiplay=False,bIsPvP=False,bCanPickupOtherGuildDeathPenaltyDrop=False,bEnableNonLoginPenalty=True,bEnableFastTravel=True,bIsStartLocationSelectByMap=True,bExistPlayerAfterLogout=False,bEnableDefenseOtherGuildPlayer=False,CoopPlayerMaxNum=4,ServerPlayerMaxNum=32,ServerName="Default Palworld Server",ServerDescription="",AdminPassword="",ServerPassword="",PublicPort=8211,PublicIP="",RCONEnabled=False,RCONPort=25575,Region="",bUseAuth=True,BanListURL="https://api.palworldgame.com/api/banlist.txt")
```

Restart server after changes.

### Backup World
```powershell
docker compose stop
tar -czf "palworld-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss').tar.gz" data/Pal/Saved/SaveGames/
docker compose start
```

### Restore World
```powershell
docker compose stop
Remove-Item -Recurse -Force data/Pal/Saved/SaveGames/
tar -xzf palworld-backup-YYYYMMDD-HHmmss.tar.gz
docker compose start
```

### Update Server
```yaml
environment:
  - UPDATE_ON_BOOT=true
```

Or manually:
```powershell
docker compose pull
docker compose up -d
```

### Use RCON
Enable in settings.ini:
```ini
RCONEnabled=True
RCONPort=25575
```

Access:
```powershell
docker exec -it palworld rcon-cli
```

RCON commands:
- `Info` - Server info
- `ShowPlayers` - Online players
- `KickPlayer <SteamID>` - Kick player
- `BanPlayer <SteamID>` - Ban player
- `Broadcast <Message>` - Broadcast message
- `Shutdown <Seconds> <Message>` - Shutdown with warning
- `DoExit` - Immediate shutdown
- `Save` - Force save

## Integration Points

### Homepage Dashboard
```yaml
- Palworld:
    icon: palworld.png
    href: palworld://server-ip:8211
    description: Palworld survival server
```

### Port Forwarding
Router configuration:
- External port: 8211 UDP
- Internal IP: Server IP
- Internal port: 8211

## Troubleshooting

### Server Won't Start
1. Check logs: `docker logs palworld`
2. Verify disk space (game is ~8GB)
3. Check port 8211 not in use
4. Ensure SteamCMD download completed

### Cannot Connect
1. Verify server is running: `docker ps`
2. Check port forwarding on router
3. Test with local IP first
4. Check firewall rules (UDP 8211)
5. Verify password matches if set

### Lag/Performance Issues
1. Reduce server player count
2. Increase container resources
3. Reduce world spawn rates
4. Disable non-essential features
5. Monitor: `docker stats palworld`

### Save Game Corruption
1. Stop server immediately
2. Restore from backup
3. Check disk space and health
4. Implement automated backups

## Best Practices

1. **Regular Backups**: Automate daily world backups
2. **Admin Password**: Strong admin password for RCON
3. **Player Limit**: 16-32 players for optimal performance
4. **Update Schedule**: Update during off-peak hours
5. **Difficulty**: Adjust rates for desired gameplay balance
6. **PvP Settings**: Clearly communicate PvP rules
7. **Port Forwarding**: Ensure UDP 8211 is forwarded

## Security Considerations

- **Admin Password**: Strong RCON password
- **Server Password**: Protect private servers
- **Port Exposure**: Only expose 8211 UDP
- **RCON Port**: Don't expose 25575 publicly
- **Player Authentication**: Use Steam auth
- **Ban List**: Update ban list URL regularly

## Advanced Configuration

### Custom Rates
Adjust gameplay in settings.ini:
```ini
ExpRate=2.000000  # 2x experience
PalCaptureRate=1.500000  # 50% easier captures
CollectionDropRate=2.000000  # 2x resource drops
WorkSpeedRate=1.500000  # 50% faster base work
```

### PvP Settings
```ini
bIsPvP=True
bEnablePlayerToPlayerDamage=True
bEnableFriendlyFire=True
bCanPickupOtherGuildDeathPenaltyDrop=True
```

### Raid Settings
```ini
bEnableInvaderEnemy=True  # Enable raids
bEnableDefenseOtherGuildPlayer=True  # Guild defense
```

### Guild Settings
```ini
GuildPlayerMaxNum=20  # Max guild size
BaseCampMaxNum=128  # Max bases per guild
BaseCampWorkerMaxNum=15  # Max workers per base
```

### Death Penalty
```ini
DeathPenalty=All  # All, Item, ItemAndEquipment, None
```

### Day/Night Cycle
```ini
DayTimeSpeedRate=1.000000  # 1x day speed
NightTimeSpeedRate=1.000000  # 1x night speed
```

## Performance Tuning

### Resource Allocation
```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 8G
    reservations:
      cpus: '2.0'
      memory: 4G
```

### Multithreading
```yaml
environment:
  - MULTITHREADING=true
```

Improves performance on multi-core systems.

### Region Lock
```yaml
environment:
  - REGION=NA  # NA, EU, AS, etc.
```

Reduces latency for region-specific players.

## Automated Backups

### Backup Script (PowerShell)
```powershell
# palworld-backup.ps1
$BackupDir = "..\..\Backups\Palworld"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupFile = "$BackupDir\palworld-save-$Timestamp.tar.gz"

# Force save via RCON
docker exec palworld rcon-cli Save
Start-Sleep -Seconds 10

# Stop server
docker compose stop
Start-Sleep -Seconds 5

# Backup saves
tar -czf $BackupFile -C ..\Docker\palworld\data\Pal\Saved SaveGames

# Restart server
docker compose start

# Keep only last 7 backups
Get-ChildItem $BackupDir -Filter "palworld-save-*.tar.gz" | 
  Sort-Object LastWriteTime -Descending | 
  Select-Object -Skip 7 | 
  Remove-Item
```

### Schedule with Task Scheduler
```powershell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File ..\Scripts\palworld-backup.ps1"
$Trigger = New-ScheduledTaskTrigger -Daily -At 4am
Register-ScheduledTask -TaskName "Palworld Backup" -Action $Action -Trigger $Trigger
```

## Monitoring

### Server Logs
```powershell
docker logs -f palworld
```

### Player List (RCON)
```powershell
docker exec palworld rcon-cli ShowPlayers
```

### Performance
```powershell
docker stats palworld
```

### Server Status
```powershell
docker exec palworld rcon-cli Info
```

## Common Settings Explained

- **ServerPlayerMaxNum**: Max concurrent players (4-32)
- **CoopPlayerMaxNum**: Max players in co-op group (1-4)
- **Difficulty**: None (custom), Normal, Hard
- **bEnablePlayerToPlayerDamage**: PvP damage
- **bEnableFriendlyFire**: Damage to allies
- **bEnableInvaderEnemy**: Enable raids on bases
- **ExpRate**: Experience multiplier
- **PalCaptureRate**: Capture difficulty (higher = easier)
- **DeathPenalty**: Items dropped on death
- **DropItemAliveMaxHours**: Dropped item despawn time
- **bEnableFastTravel**: Allow fast travel
- **bUseAuth**: Require Steam authentication

This Palworld dedicated server configuration enables private multiplayer creature-collecting survival gameplay with extensive customization options in the Docker gaming server stack.
