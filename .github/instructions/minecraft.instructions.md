---
applyTo: "minecraft/**"
---

# Minecraft Server Expert Instructions

You are an expert in Minecraft dedicated server management using itzg/minecraft-server Docker image.

## Service Overview
Minecraft server for vanilla or modded multiplayer gameplay. The itzg/minecraft-server Docker image provides automated server setup with extensive customization options for Java Edition servers.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "25565:25565"  # Java Edition default port
environment:
  - EULA=TRUE
  - TYPE=VANILLA  # Or FORGE, FABRIC, PAPER, SPIGOT
  - VERSION=LATEST  # Or specific: 1.20.4
  - MEMORY=2G
  - DIFFICULTY=normal
  - MODE=survival
  - MAX_PLAYERS=20
  - MOTD=My Minecraft Server
  - ENABLE_RCON=true
  - RCON_PASSWORD=minecraft
volumes:
  - ./data:/data
restart: unless-stopped
```

### Critical Files
- `data/server.properties` - Server configuration
- `data/ops.json` - Server operators
- `data/whitelist.json` - Whitelisted players
- `data/banned-players.json` - Banned players
- `data/world/` - World save data
- `data/logs/` - Server logs

### Default Port
- 25565 - Minecraft Java Edition

## Common Tasks

### First-Time Setup
1. Set `EULA=TRUE` in docker-compose.yml (accept Mojang EULA)
2. Start container
3. Wait for world generation (check logs)
4. Connect: `localhost:25565` or `server-ip:25565`

### Make Yourself an Operator
```powershell
docker exec minecraft rcon-cli op YourUsername
```

Or add to ops.json before first start:
```json
[
  {
    "uuid": "player-uuid",
    "name": "YourUsername",
    "level": 4,
    "bypassesPlayerLimit": false
  }
]
```

Get UUID from https://mcuuid.net/

### Change Server Settings
Edit server.properties or use environment variables:
```yaml
environment:
  - DIFFICULTY=hard
  - MODE=survival
  - MAX_PLAYERS=20
  - SPAWN_PROTECTION=16
  - PVP=true
  - VIEW_DISTANCE=10
  - SIMULATION_DISTANCE=10
  - ENABLE_COMMAND_BLOCK=true
```

Restart container to apply.

### Whitelist Players
```powershell
docker exec minecraft rcon-cli whitelist add PlayerName
docker exec minecraft rcon-cli whitelist on
```

Or edit whitelist.json:
```json
[
  {
    "uuid": "player-uuid",
    "name": "PlayerName"
  }
]
```

### Ban/Unban Players
```powershell
docker exec minecraft rcon-cli ban PlayerName Reason
docker exec minecraft rcon-cli pardon PlayerName
```

### World Backup
```powershell
docker exec minecraft rcon-cli save-off
docker exec minecraft rcon-cli save-all flush
tar -czf "minecraft-world-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss').tar.gz" data/world/
docker exec minecraft rcon-cli save-on
```

### Restore World
```powershell
docker compose stop
Remove-Item -Recurse -Force data/world/
tar -xzf minecraft-world-backup-YYYYMMDD-HHmmss.tar.gz
docker compose start
```

## Integration Points

### RCON (Remote Console)
Enable in docker-compose.yml:
```yaml
environment:
  - ENABLE_RCON=true
  - RCON_PASSWORD=secure_password
  - RCON_PORT=25575
ports:
  - "25575:25575"
```

Use RCON client:
```powershell
docker exec minecraft rcon-cli
# Or external tool with host:port and password
```

### Homepage Dashboard
```yaml
- Minecraft:
    icon: minecraft.png
    href: minecraft://server-ip:25565
    description: Minecraft survival server
    widget:
      type: minecraft
      url: udp://minecraft:25565
```

### Port Forwarding
Router configuration:
- External port: 25565 TCP
- Internal IP: Server IP
- Internal port: 25565

### Dynmap (Web Map)
For PAPER/SPIGOT servers with Dynmap plugin:
```yaml
ports:
  - "8123:8123"
```
Access: `http://server-ip:8123`

### Nginx Proxy Manager (for Dynmap)
```
Domain: map.minecraft.benlawson.dev
Forward: http://minecraft:8123
SSL: Let's Encrypt
```

## Troubleshooting

### Server Won't Start
1. Check EULA=TRUE is set
2. Review logs: `docker logs minecraft`
3. Check Java memory allocation
4. Verify world files not corrupted
5. Check port 25565 not in use

### Cannot Connect
1. Verify server is running: `docker ps`
2. Check port forwarding on router
3. Test locally: `localhost:25565`
4. Check firewall rules
5. Verify server-ip in client matches actual IP

### Out of Memory Errors
Increase memory:
```yaml
environment:
  - MEMORY=4G  # Up from 2G
```

Monitor usage:
```powershell
docker stats minecraft
```

### World Corruption
1. Stop server immediately
2. Restore from backup
3. Check disk space and health
4. Consider daily automated backups

### Lag Issues
1. Reduce view-distance: 6-8 chunks
2. Reduce simulation-distance: 6-8 chunks
3. Install optimization plugins (Paper, Lithium)
4. Limit entities/mobs
5. Pregenerate world with Chunky plugin

## Best Practices

1. **Regular Backups**: Automate daily world backups
2. **Operators**: Limit OP access to trusted players
3. **Whitelist**: Use whitelist for private servers
4. **View Distance**: Balance performance vs. render distance
5. **Memory**: Allocate 2GB minimum, 4-8GB for modded
6. **Server Type**: Use Paper for performance optimizations
7. **Updates**: Pin VERSION to avoid unexpected breaking changes

## Security Considerations

- **RCON Password**: Strong password, don't expose publicly
- **Whitelist**: Enable for private servers
- **Port Exposure**: Only expose 25565, not RCON or debug ports
- **Operators**: Limit to trusted admins
- **Command Blocks**: Disable if not needed
- **Plugins**: Only install from trusted sources (Spigot, Bukkit, Modrinth)

## Advanced Configuration

### Server Types

**Vanilla**:
```yaml
- TYPE=VANILLA
- VERSION=1.20.4
```

**Paper** (optimized):
```yaml
- TYPE=PAPER
- VERSION=1.20.4
```

**Forge** (mods):
```yaml
- TYPE=FORGE
- VERSION=1.20.1
- FORGEVERSION=47.2.0  # Specific Forge version
```

**Fabric** (lightweight mods):
```yaml
- TYPE=FABRIC
- VERSION=1.20.4
- FABRIC_LOADER_VERSION=0.15.3
```

**Modpacks** (CurseForge):
```yaml
- TYPE=CURSEFORGE
- CF_SERVER_MOD=https://www.curseforge.com/minecraft/modpacks/all-the-mods-9/files/5073141
```

### Plugins (Paper/Spigot)
Auto-download plugins:
```yaml
environment:
  - SPIGET_RESOURCES=9089,34315  # EssentialsX, Vault plugin IDs
```

Or mount plugins directory:
```yaml
volumes:
  - ./data:/data
  - ./plugins:/plugins:ro
```

Place .jar files in `./plugins/` directory.

### Datapacks
```yaml
volumes:
  - ./datapacks:/data/world/datapacks:ro
```

Place datapacks in `./datapacks/` directory.

### Custom server.properties
Mount custom config:
```yaml
volumes:
  - ./server.properties:/data/server.properties:ro
```

Overrides environment variables.

### Mod Installation (Forge/Fabric)
```yaml
volumes:
  - ./mods:/data/mods:ro
```

Place mod .jar files in `./mods/` directory. Ensure client and server have compatible mods.

## Performance Tuning

### JVM Flags (Aikar's Flags)
```yaml
environment:
  - JVM_OPTS=-Xms2G -Xmx2G -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1
```

Optimizes Java garbage collection for Minecraft.

### Server Settings
```properties
view-distance=8
simulation-distance=6
max-tick-time=60000
entity-broadcast-range-percentage=100
```

Balance performance vs. gameplay quality.

### Pregenerate World
Install Chunky plugin:
```
/chunky radius 5000
/chunky world world
/chunky start
```

Generates chunks before players explore, reduces lag.

## RCON Commands

### Basic Commands
```powershell
docker exec minecraft rcon-cli list  # Online players
docker exec minecraft rcon-cli say Hello  # Broadcast message
docker exec minecraft rcon-cli stop  # Graceful shutdown
```

### Player Management
```powershell
docker exec minecraft rcon-cli kick PlayerName Reason
docker exec minecraft rcon-cli ban PlayerName Reason
docker exec minecraft rcon-cli op PlayerName
docker exec minecraft rcon-cli deop PlayerName
docker exec minecraft rcon-cli whitelist add PlayerName
```

### World Management
```powershell
docker exec minecraft rcon-cli save-all  # Save world
docker exec minecraft rcon-cli save-off  # Disable auto-save
docker exec minecraft rcon-cli save-on  # Enable auto-save
docker exec minecraft rcon-cli time set day
docker exec minecraft rcon-cli weather clear
docker exec minecraft rcon-cli difficulty hard
```

### Server Info
```powershell
docker exec minecraft rcon-cli seed  # World seed
docker exec minecraft rcon-cli gamerule <rule> <value>
```

## Automated Backups

### Backup Script (PowerShell)
```powershell
# minecraft-backup.ps1
$BackupDir = "..\..\Backups\Minecraft"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupFile = "$BackupDir\minecraft-world-$Timestamp.tar.gz"

# Save and pause autosave
docker exec minecraft rcon-cli save-off
docker exec minecraft rcon-cli save-all flush
Start-Sleep -Seconds 5

# Backup world
tar -czf $BackupFile -C ..\Docker\minecraft\data world

# Resume autosave
docker exec minecraft rcon-cli save-on

# Keep only last 7 backups
Get-ChildItem $BackupDir -Filter "minecraft-world-*.tar.gz" | 
  Sort-Object LastWriteTime -Descending | 
  Select-Object -Skip 7 | 
  Remove-Item
```

### Schedule with Task Scheduler
```powershell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File ..\Scripts\minecraft-backup.ps1"
$Trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "Minecraft Backup" -Action $Action -Trigger $Trigger
```

## Monitoring

### Server Logs
```powershell
docker logs -f minecraft
```

### Player Activity
```powershell
docker exec minecraft rcon-cli list
```

### Performance
```powershell
docker stats minecraft
docker exec minecraft rcon-cli forge tps  # If Forge
```

### Plugin: Spark (Profiler)
Install Spark plugin for detailed performance profiling:
```
/spark profiler
```

## Common Server Properties

```properties
difficulty=normal  # peaceful, easy, normal, hard
gamemode=survival  # survival, creative, adventure, spectator
max-players=20
pvp=true
view-distance=10  # chunks
spawn-protection=16  # blocks
enable-command-block=false
max-world-size=29999984
motd=A Minecraft Server
server-port=25565
allow-flight=false
hardcore=false
```

## Version Pinning

Prevent automatic updates:
```yaml
environment:
  - VERSION=1.20.4
```

Or use specific Docker image tag:
```yaml
image: itzg/minecraft-server:java17-alpine
```

This ensures consistent gameplay and prevents breaking changes from updates.

## World Seeds

Set specific world seed:
```yaml
environment:
  - SEED=-1234567890
```

Generates same world layout for all players.

This comprehensive Minecraft server configuration enables multiplayer Java Edition gameplay with extensive customization options for mods, plugins, and performance tuning in the Docker homelab.
