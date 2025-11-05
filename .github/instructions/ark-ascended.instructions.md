---
applyTo: "ark-ascended/**"
---

# ARK: Survival Ascended Server Expert Instructions

You are an expert in ARK: Survival Ascended dedicated server management (Unreal Engine 5 remake).

## Service Overview
ARK: Survival Ascended is the complete remake of ARK: Survival Evolved built on Unreal Engine 5. It features enhanced graphics, improved performance, and cross-platform play. This is a separate game from the original ARK with different server requirements.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "7777:7777/udp"  # Game port
  - "7778:7778/udp"  # Raw UDP socket
  - "27015:27015/udp"  # Query port
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/Chicago
  - SERVER_NAME=My ASA Server
  - SERVER_PASSWORD=
  - ADMIN_PASSWORD=admin123
  - MAX_PLAYERS=70
  - MAP_NAME=TheIsland_WP
  - MODS=  # Mod IDs comma-separated
  - RCON_ENABLED=true
  - RCON_PORT=27020
volumes:
  - ./config:/ark
  - E:\Docker\ark-ascended\Game.ini:/ark/ShooterGame/Saved/Config/WindowsServer/Game.ini
  - E:\Docker\ark-ascended\GameUserSettings.ini:/ark/ShooterGame/Saved/Config/WindowsServer/GameUserSettings.ini
restart: unless-stopped
deploy:
  resources:
    limits:
      memory: 16G  # ASA requires more RAM than original ARK
    reservations:
      memory: 12G
cap_add:
  - sys_nice
stop_grace_period: 180s  # Longer save time for UE5
```

### Critical Files
- `config/ShooterGame/Saved/Config/WindowsServer/GameUserSettings.ini` - Main config
- `config/ShooterGame/Saved/Config/WindowsServer/Game.ini` - Advanced settings
- `config/ShooterGame/Saved/SavedArks/` - World saves
- `Game.ini` - Pre-configured game settings (mounted)
- `GameUserSettings.ini` - Pre-configured user settings (mounted)

### Default Ports
- 7777/UDP - Game connection
- 7778/UDP - Raw UDP socket
- 27015/UDP - Steam query port
- 27020/TCP - RCON (if enabled)

## Common Tasks

### First-Time Setup
1. Create Game.ini and GameUserSettings.ini in ark-ascended directory
2. Start container (downloads game ~30-40GB)
3. Wait for "Server ready" message (~15-20 minutes first start)
4. Connect in-game: `server-ip:7777`

### Connect to Server
In ASA client:
1. Server Browser > Favorites
2. Add server: `your-ip:7777`
3. Connect (enter password if set)

### Configure Server Settings
Edit `GameUserSettings.ini`:
```ini
[ServerSettings]
ServerName=My ASA Server
ServerPassword=
ServerAdminPassword=admin123
MaxPlayers=70
DifficultyOffset=1.0
ServerPVE=False
ServerCrosshair=True
ServerForceNoHUD=False
ShowMapPlayerLocation=True
EnablePVPGamma=True
RCONEnabled=True
RCONPort=27020
TheMaxStructuresInRange=10500

[/Script/ShooterGame.ShooterGameMode]
bDisableStructureDecayPvE=False
bAllowFlyerCarryPvE=True
MaxTamedDinos=5000
```

Edit `Game.ini`:
```ini
[/Script/ShooterGame.ShooterGameMode]
ConfigOverrideItemMaxQuantity=(ItemClassString="PrimalItemConsumable_Berry_Mejoberry_C",Quantity=(MaxItemQuantity=999,ItemQuantity=999))
```

Restart container after changes.

### Backup World Save
```powershell
docker exec ark-ascended rcon-cli SaveWorld
Start-Sleep -Seconds 30
tar -czf "asa-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss').tar.gz" -C config/ShooterGame/Saved SavedArks/
```

### Restore World Save
```powershell
docker compose stop
Remove-Item -Recurse -Force config/ShooterGame/Saved/SavedArks/
tar -xzf asa-backup-YYYYMMDD-HHMMSS.tar.gz -C config/ShooterGame/Saved/
docker compose start
```

### Install Mods
```yaml
environment:
  - MODS=123456,789012  # CurseForge mod IDs
```

Mods auto-download on server start.

### Use RCON
```powershell
docker exec ark-ascended rcon-cli
```

Common RCON commands:
- `SaveWorld` - Force save
- `Broadcast <message>` - Server announcement
- `ListPlayers` - Online players
- `KickPlayer <SteamID>` - Kick player
- `BanPlayer <SteamID>` - Ban player
- `ServerChat <message>` - Server chat message
- `DoExit` - Shutdown server

## Integration Points

### Homepage Dashboard
```yaml
- ARK Survival Ascended:
    icon: ark.png
    href: ark://your-ip:7777
    description: ARK UE5 remake server
```

### Port Forwarding
Router configuration:
- External: 7777-7778 UDP
- External: 27015 UDP
- Internal IP: Server IP
- Internal: Same ports

## Troubleshooting

### Server Won't Start
1. Check logs: `docker logs ark-ascended`
2. Verify disk space (ASA is ~30-40GB)
3. Check memory allocation (12-16GB minimum)
4. Verify Game.ini and GameUserSettings.ini exist
5. Check ports not in use

### Cannot Connect
1. Verify server is running: `docker ps`
2. Check port forwarding on router
3. Test with local IP first
4. Check firewall rules (UDP 7777-7778, 27015)
5. Verify server appears in Steam server browser

### Performance Issues
1. Increase memory allocation: 16-20GB
2. ASA requires powerful CPU (8+ cores recommended)
3. Reduce view distance settings
4. Limit wild dino count
5. Monitor: `docker stats ark-ascended`
6. Consider SSD for game files

### Save Corruption
1. Stop server immediately
2. Restore from backup
3. Implement automated backups
4. Check disk health and space

### Mods Not Loading
1. Verify mod IDs are correct (CurseForge IDs)
2. Check mod compatibility with server version
3. Review mod load order
4. Some mods require specific Game.ini settings

## Best Practices

1. **Memory**: 16GB minimum for stable operation
2. **CPU**: 8+ cores recommended (UE5 is CPU-intensive)
3. **Storage**: SSD strongly recommended
4. **Regular Backups**: Automate daily world backups
5. **Admin Password**: Strong RCON password
6. **Graceful Shutdown**: Allow 180s for world save
7. **Updates**: ASA updates frequently, monitor changelogs

## Security Considerations

- **Admin Password**: Strong RCON password
- **Server Password**: Protect private servers
- **Port Exposure**: Only expose 7777-7778, 27015
- **RCON Port**: Don't expose 27020 publicly
- **Steam Integration**: Required for authentication
- **Mod Security**: Only install trusted mods

## Advanced Configuration

### Multipliers Configuration
GameUserSettings.ini:
```ini
[ServerSettings]
XPMultiplier=2.0
TamingSpeedMultiplier=3.0
HarvestAmountMultiplier=2.0
HarvestHealthMultiplier=2.0
ResourcesRespawnPeriodMultiplier=0.5
PlayerCharacterHealthRecoveryMultiplier=2.0
PlayerCharacterStaminaDrainMultiplier=0.5
PlayerCharacterFoodDrainMultiplier=0.5
DinoCharacterHealthMultiplier=1.5
DinoCharacterStaminaMultiplier=1.5
```

### PvP/PvE Settings
```ini
[ServerSettings]
ServerPVE=False  # True for PvE
EnablePVPGamma=True
DisablePvEGamma=False
AllowCaveBuildingPvE=True
PreventDownloadSurvivors=False
PreventDownloadItems=False
PreventDownloadDinos=False
```

### Breeding Settings
```ini
MatingIntervalMultiplier=0.5
EggHatchSpeedMultiplier=10.0
BabyMatureSpeedMultiplier=10.0
BabyImprintingStatScaleMultiplier=2.0
BabyCuddleIntervalMultiplier=0.5
```

### Day/Night Cycle
```ini
DayCycleSpeedScale=1.0
NightTimeSpeedScale=1.0
DayTimeSpeedScale=1.0
```

### Structure Settings
```ini
TheMaxStructuresInRange=10500
MaxStructuresInSmallRadius=100
```

## Available Maps

**Base Game**:
- **TheIsland_WP** - Original island map (remake)

**DLC Maps** (coming):
- ScorchedEarth_WP
- Aberration_WP
- Extinction_WP
- Genesis_WP
- And more as released

## Performance Tuning

### Resource Allocation
```yaml
deploy:
  resources:
    limits:
      cpus: '8.0'
      memory: 20G
    reservations:
      cpus: '4.0'
      memory: 16G
```

### Graphics Settings (Server)
Game.ini:
```ini
[/Script/Engine.GameUserSettings]
sg.ViewDistanceQuality=0
sg.AntiAliasingQuality=0
sg.ShadowQuality=0
sg.PostProcessQuality=0
sg.TextureQuality=0
sg.EffectsQuality=0
sg.FoliageQuality=0
```

### Wild Dino Management
```
destroywilddinos  # Admin command to refresh spawns
```

## System Requirements

### Minimum
- CPU: 8 cores
- RAM: 12GB
- Storage: 50GB SSD
- Network: 100Mbps

### Recommended
- CPU: 12+ cores (Ryzen 5600X or better)
- RAM: 16-20GB
- Storage: 100GB NVMe SSD
- Network: 1Gbps

## Differences from Original ARK

1. **Engine**: Unreal Engine 5 (vs UE4)
2. **Graphics**: Significantly enhanced visuals
3. **Performance**: Better optimization (when properly configured)
4. **Cross-Platform**: PC and Console cross-play
5. **Mod Support**: CurseForge integration
6. **File Size**: Larger installation (~40GB vs ~20GB)
7. **RAM Usage**: Higher memory requirements
8. **Updates**: More frequent updates and patches

## Automated Backups

### Backup Script (PowerShell)
```powershell
# asa-backup.ps1
$BackupDir = "E:\Backups\ASA"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupFile = "$BackupDir\asa-save-$Timestamp.tar.gz"

# Force save via RCON
docker exec ark-ascended rcon-cli SaveWorld
Start-Sleep -Seconds 60

# Stop server for consistent backup
docker compose -f E:\Docker\ark-ascended\docker-compose.yml stop
Start-Sleep -Seconds 10

# Backup save files
tar -czf $BackupFile -C E:\Docker\ark-ascended\config\ShooterGame\Saved SavedArks

# Restart server
docker compose -f E:\Docker\ark-ascended\docker-compose.yml start

# Keep only last 7 backups
Get-ChildItem $BackupDir -Filter "asa-save-*.tar.gz" | 
  Sort-Object LastWriteTime -Descending | 
  Select-Object -Skip 7 | 
  Remove-Item

Write-Host "Backup complete: $BackupFile"
```

### Schedule with Task Scheduler
```powershell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File E:\Scripts\asa-backup.ps1"
$Trigger = New-ScheduledTaskTrigger -Daily -At 5am
Register-ScheduledTask -TaskName "ASA Backup" -Action $Action -Trigger $Trigger
```

## Monitoring

### Server Logs
```powershell
docker logs -f ark-ascended
```

### Player List (RCON)
```powershell
docker exec ark-ascended rcon-cli ListPlayers
```

### Performance
```powershell
docker stats ark-ascended
```

### Server Info
```powershell
docker exec ark-ascended rcon-cli GetGameLog
```

## Common Admin Commands

### Player Management
```
ShowMessageOfTheDay
ListPlayers
KickPlayer <SteamID>
BanPlayer <SteamID>
UnbanPlayer <SteamID>
AllowPlayerToJoinNoCheck <SteamID>
```

### World Management
```
SaveWorld
DestroyWildDinos
DestroyAllEnemies
SetTimeOfDay 12:00:00
```

### Server Management
```
Broadcast <message>
ServerChat <message>
DoExit
```

This Unreal Engine 5 remake of ARK provides enhanced graphics and performance with cross-platform support, requiring more system resources but delivering improved gameplay experience for the Docker gaming server stack.
