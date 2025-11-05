---
applyTo: "ark/**"
---

# ARK: Survival Evolved Server Expert Instructions

You are an expert in ARK: Survival Evolved dedicated server management (legacy version, not Ascended).

## Service Overview
ARK: Survival Evolved is a survival game featuring dinosaurs and prehistoric creatures. This is the original ARK game (before ARK: Survival Ascended). The server must be run from WSL due to Windows filesystem performance limitations.

## Technical Configuration

### WSL Requirement
**CRITICAL**: ARK server must run in WSL (Windows Subsystem for Linux) due to severe performance issues with Windows filesystem:
- Windows host: 10+ minute load times
- WSL: 30 second load times

Deploy from WSL terminal:
```bash
cd /mnt/e/Docker/ark
docker compose up -d
```

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
  - SESSION_NAME=My ARK Server
  - SERVER_PASSWORD=  # Optional
  - ADMIN_PASSWORD=admin123
  - SERVER_MAP=TheIsland
  - MAX_PLAYERS=70
  - RCON_ENABLED=true
  - RCON_PORT=32330
volumes:
  - ./config:/ark
restart: unless-stopped
deploy:
  resources:
    limits:
      memory: 8G
    reservations:
      memory: 6G
cap_add:
  - sys_nice  # Priority scheduling
stop_grace_period: 120s  # Allow graceful shutdown
```

### Critical Files
- `config/ShooterGame/Saved/Config/LinuxServer/GameUserSettings.ini` - Main config
- `config/ShooterGame/Saved/Config/LinuxServer/Game.ini` - Advanced settings
- `config/ShooterGame/Saved/SavedArks/` - World saves
- `config/ShooterGame/Binaries/Linux/ShooterGameServer` - Server binary

### Default Ports
- 7777/UDP - Game connection
- 7778/UDP - Raw UDP socket
- 27015/UDP - Steam query port
- 32330/TCP - RCON (if enabled)

## Common Tasks

### First-Time Setup (from WSL)
```bash
cd /mnt/e/Docker/ark
docker compose up -d
docker logs -f ark
# Wait for "Server ready" message (~10-15 minutes first start)
```

### Connect to Server
In ARK client:
1. Steam > View > Servers > Favorites
2. Add server: `your-ip:7777`
3. Connect (enter password if set)

### Admin Commands
Join server, press TAB, then:
```
enablecheats admin123
setplayerpos 0 0 0
destroywilddinos
saveworld
```

### Configure Server Settings
Edit `config/ShooterGame/Saved/Config/LinuxServer/GameUserSettings.ini`:
```ini
[ServerSettings]
SessionName=My ARK Server
MaxPlayers=70
ServerPassword=
ServerAdminPassword=admin123
DifficultyOffset=1.0
XPMultiplier=2.0
TamingSpeedMultiplier=3.0
HarvestAmountMultiplier=2.0
ResourcesRespawnPeriodMultiplier=0.5
PlayerCharacterWaterDrainMultiplier=0.5
PlayerCharacterFoodDrainMultiplier=0.5
AllowThirdPersonPlayer=True
ShowMapPlayerLocation=True
ServerCrosshair=True
```

Restart container after changes.

### Backup World Save
```bash
docker exec ark rcon-cli SaveWorld
sleep 30
tar -czf "ark-backup-$(date +%Y%m%d-%H%M%S).tar.gz" -C config/ShooterGame/Saved SavedArks/
```

### Restore World Save
```bash
docker stop ark
cd config/ShooterGame/Saved
rm -rf SavedArks/
tar -xzf /path/to/ark-backup-YYYYMMDD-HHMMSS.tar.gz
docker start ark
```

### Change Map
Edit docker-compose.yml:
```yaml
- SERVER_MAP=Ragnarok  # TheIsland, TheCenter, Ragnarok, Valguero, etc.
```

Restart container (new world starts).

### Use RCON
```bash
docker exec ark rcon-cli
```

Or external tool with host:32330 and password.

Common RCON commands:
- `SaveWorld` - Force save
- `Broadcast <message>` - Server announcement
- `ListPlayers` - Online players
- `KickPlayer <name>` - Kick player
- `BanPlayer <name>` - Ban player
- `DoExit` - Shutdown server

## Integration Points

### Homepage Dashboard
```yaml
- ARK Survival Evolved:
    icon: ark.png
    href: ark://your-ip:7777
    description: Dinosaur survival server
```

### Port Forwarding
Router configuration:
- External: 7777-7778 UDP
- External: 27015 UDP
- Internal IP: Server IP
- Internal: Same ports

## Troubleshooting

### Extremely Slow Loading (10+ minutes)
**Cause**: Running on Windows filesystem
**Fix**: MUST run from WSL:
```bash
cd /mnt/e/Docker/ark
docker compose up -d
```

### Server Won't Start
1. Check logs: `docker logs ark`
2. Verify disk space (ARK is ~20-30GB)
3. Check memory allocation (6-8GB minimum)
4. Verify WSL deployment
5. Check ports not in use

### Cannot Connect
1. Verify server is running: `docker ps`
2. Check port forwarding on router
3. Test with local IP first: `192.168.x.x:7777`
4. Check firewall rules (UDP 7777-7778, 27015)
5. Verify Steam query port working

### Lag/Performance Issues
1. Increase memory allocation: 8-10GB
2. Reduce max players
3. Disable some wild dino spawns
4. Reduce view distance
5. Monitor: `docker stats ark`
6. Check CPU usage (ARK is CPU-intensive)

### Save Corruption
1. Stop server immediately
2. Restore from backup
3. Check disk health
4. Implement automated backups

### Mods Not Loading
1. Verify mod IDs in GameUserSettings.ini
2. Check SteamCMD downloaded mods
3. Review mod compatibility
4. Some mods conflict with each other

## Best Practices

1. **WSL Deployment**: ALWAYS run from WSL for performance
2. **Regular Backups**: Automate daily world backups
3. **Admin Password**: Strong RCON password
4. **Memory**: 8GB minimum for stable operation
5. **Graceful Shutdown**: Allow 120s for world save
6. **Multipliers**: Balance harvest/taming for desired gameplay
7. **Updates**: Pin version or update during off-peak hours

## Security Considerations

- **Admin Password**: Strong RCON password
- **Server Password**: Protect private servers
- **Port Exposure**: Only expose 7777-7778, 27015
- **RCON Port**: Don't expose 32330 publicly without VPN
- **Tribe Settings**: Configure PvE/PvP boundaries
- **Player Reporting**: Enable logging for abuse

## Advanced Configuration

### Multipliers Configuration
GameUserSettings.ini:
```ini
[ServerSettings]
# Experience
XPMultiplier=2.0

# Taming
TamingSpeedMultiplier=3.0

# Harvesting
HarvestAmountMultiplier=2.0
HarvestHealthMultiplier=2.0

# Resource Respawn
ResourcesRespawnPeriodMultiplier=0.5

# Player Stats
PlayerCharacterHealthRecoveryMultiplier=2.0
PlayerCharacterStaminaDrainMultiplier=0.5
PlayerCharacterFoodDrainMultiplier=0.5
PlayerCharacterWaterDrainMultiplier=0.5

# Dino Stats
DinoCharacterHealthMultiplier=1.5
DinoCharacterStaminaMultiplier=1.5
DinoCharacterFoodDrainMultiplier=0.5
```

### Mod Configuration
GameUserSettings.ini:
```ini
[ServerSettings]
ActiveMods=731604991,899987403,895711211
```

Mod IDs from Steam Workshop.

### Custom Engrams
Game.ini:
```ini
[/Script/ShooterGame.ShooterGameMode]
OverrideEngramEntries=(EngramIndex=0,EngramHidden=False,EngramPointsCost=0,EngramLevelRequirement=1,RemoveEngramPreReq=True)
```

### PvP/PvE Settings
GameUserSettings.ini:
```ini
[ServerSettings]
ServerPVE=False  # True for PvE, False for PvP
EnablePVPGamma=True
DisablePvEGamma=False
AllowCaveBuildingPvE=True
```

### Tribe Settings
```ini
MaxTribeLogs=100
TribeNameChangeCooldown=86400
```

### Day/Night Cycle
```ini
DayCycleSpeedScale=1.0
NightTimeSpeedScale=1.0
DayTimeSpeedScale=1.0
```

### Difficulty and Levels
```ini
DifficultyOffset=1.0  # 0.0-1.0, affects dino levels
OverrideOfficialDifficulty=5.0  # Max dino level multiplier
```

## Available Maps

- **TheIsland** - Original map
- **TheCenter** - Community map, large caves
- **Scorched Earth** - Desert, extreme weather (paid DLC)
- **Ragnarok** - Huge varied map (free)
- **Aberration** - Underground caverns (paid DLC)
- **Extinction** - Post-apocalyptic (paid DLC)
- **Valguero** - Norse-themed (free)
- **Genesis Part 1** - Biome simulation (paid DLC)
- **Genesis Part 2** - Space-themed (paid DLC)
- **Crystal Isles** - Floating islands (free)
- **Lost Island** - Tropical islands (free)
- **Fjordur** - Nordic realms (free)

## Performance Tuning

### Resource Allocation
```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 10G
    reservations:
      cpus: '2.0'
      memory: 8G
```

### Reduce Wild Dino Count
Game.ini:
```ini
NPCReplacements=(FromClassName="",ToClassName="")
```

Or use admin command:
```
destroywilddinos
```

### View Distance
GameUserSettings.ini:
```ini
ViewDistance=Medium  # Low, Medium, High, Epic
```

## Automated Backups

### Backup Script (Bash)
```bash
#!/bin/bash
# ark-backup.sh
BACKUP_DIR="/mnt/e/Backups/ARK"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ark-save-$TIMESTAMP.tar.gz"

# Force save via RCON
docker exec ark rcon-cli SaveWorld
sleep 30

# Backup save files
tar -czf "$BACKUP_FILE" -C /mnt/e/Docker/ark/config/ShooterGame/Saved SavedArks

# Keep only last 7 backups
ls -t $BACKUP_DIR/ark-save-*.tar.gz | tail -n +8 | xargs -r rm

echo "Backup complete: $BACKUP_FILE"
```

### Schedule with Cron (WSL)
```bash
crontab -e
# Add line:
0 4 * * * /mnt/e/Scripts/ark-backup.sh
```

## Monitoring

### Server Logs
```bash
docker logs -f ark
```

### Player List (RCON)
```bash
docker exec ark rcon-cli ListPlayers
```

### Performance
```bash
docker stats ark
```

### Server Status
Check Steam query port:
```powershell
Invoke-RestMethod -Uri "https://api.steampowered.com/ISteamApps/GetServersAtAddress/v1/?addr=your-ip"
```

## Common Admin Commands

### Player Management
```
enablecheats admin123
listplayers
kickplayer <name>
banplayer <name>
unbanplayer <name>
```

### World Management
```
saveworld
destroywilddinos
destroyallenemies
settimeofday 12:00
```

### Player Teleport
```
setplayerpos 0 0 0
tphere <playername>
tpcoords <x> <y> <z>
```

### Give Items
```
giveitemnum <id> <quantity> <quality> <blueprint>
giveitem <path> <quantity> <quality> <blueprint>
```

### Dino Commands
```
gmsummon <type> <level>
forcetame  # Tame dino you're looking at
dotame  # Tame dino instantly
```

## File Size Estimates

- **Base Installation**: ~20GB
- **Per Save File**: 100-500MB (grows with play time)
- **Mods**: 50MB-2GB each
- **Total**: 25-40GB typical

This dinosaur survival server requires WSL deployment for optimal performance, providing immersive prehistoric gameplay with extensive customization options for the Docker gaming server stack.
