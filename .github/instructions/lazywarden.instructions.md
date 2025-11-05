---
applyTo: "lazywarden/**"
---

# Lazywarden Expert Instructions

You are an expert in Lazywarden configuration for automated Bitwarden/Vaultwarden backup management.

## Service Overview
Lazywarden is an automated backup solution specifically designed for Vaultwarden (self-hosted Bitwarden) installations. It handles scheduled backups, retention policies, compression, encryption, and optional cloud uploads to ensure password vault data is protected.

## Technical Configuration

### Docker Compose Patterns
```yaml
environment:
  - TZ=America/Chicago
  - BACKUP_SCHEDULE=0 2 * * *  # Daily at 2 AM (cron format)
  - BACKUP_RETENTION_DAYS=30
  - BACKUP_ENCRYPTION=true
  - BACKUP_ENCRYPTION_PASSWORD=${BACKUP_PASSWORD}
  - VAULTWARDEN_DATA=/vaultwarden-data
  - BACKUP_DIR=/backups
  - UPLOAD_TO_CLOUD=false  # Optional: S3, B2, etc.
volumes:
  - ../bitwarden/data:/vaultwarden-data:ro
  - ./data:/backups
  - ./config:/config
restart: unless-stopped
```

### Critical Files
- `data/` - Backup storage location
- `config/lazywarden.conf` - Configuration (if not using env vars)

### No Ports Required
Background backup service, no exposed ports.

## Common Tasks

### First-Time Setup
1. Configure Vaultwarden data path (read-only mount)
2. Set backup schedule (cron format)
3. Configure retention policy
4. Set encryption password (recommended)
5. Start container
6. Verify first backup: `docker logs lazywarden`

### Configure Backup Schedule
Use cron format:
```yaml
# Daily at 2 AM
- BACKUP_SCHEDULE=0 2 * * *

# Every 6 hours
- BACKUP_SCHEDULE=0 */6 * * *

# Weekly on Sunday at 3 AM
- BACKUP_SCHEDULE=0 3 * * 0

# Every 12 hours
- BACKUP_SCHEDULE=0 */12 * * *
```

### Manual Backup Trigger
```powershell
docker exec lazywarden /app/backup.sh
```

### View Backup History
```powershell
Get-ChildItem E:\Docker\lazywarden\data | Sort-Object LastWriteTime -Descending
```

### Restore from Backup
```powershell
# 1. Stop Vaultwarden
docker compose -f E:\Docker\bitwarden\docker-compose.yml stop

# 2. Extract backup
$BackupFile = "E:\Docker\lazywarden\data\vaultwarden-backup-20250105-020000.tar.gz.enc"

# If encrypted, decrypt first
openssl enc -d -aes-256-cbc -in $BackupFile -out vaultwarden-backup.tar.gz -k "your-encryption-password"

# 3. Extract to Vaultwarden data directory
tar -xzf vaultwarden-backup.tar.gz -C E:\Docker\bitwarden\data\

# 4. Restart Vaultwarden
docker compose -f E:\Docker\bitwarden\docker-compose.yml start
```

### Configure Retention Policy
```yaml
- BACKUP_RETENTION_DAYS=30  # Keep backups for 30 days
```

Old backups are automatically deleted.

### Enable Encryption
```yaml
- BACKUP_ENCRYPTION=true
- BACKUP_ENCRYPTION_PASSWORD=${BACKUP_PASSWORD}
```

Store password securely in .env file.

## Integration Points

### Vaultwarden
Mounts Vaultwarden data directory read-only:
```yaml
volumes:
  - ../bitwarden/data:/vaultwarden-data:ro
```

Backs up:
- SQLite database (`db.sqlite3`)
- PostgreSQL dumps (if using Postgres)
- Attachments folder
- Sends folder (encrypted messages)
- Configuration files

### Cloud Storage (Optional)
Upload backups to cloud providers:

**Amazon S3**:
```yaml
- UPLOAD_TO_CLOUD=true
- CLOUD_PROVIDER=s3
- S3_BUCKET=my-backup-bucket
- S3_REGION=us-east-1
- AWS_ACCESS_KEY_ID=${AWS_KEY}
- AWS_SECRET_ACCESS_KEY=${AWS_SECRET}
```

**Backblaze B2**:
```yaml
- CLOUD_PROVIDER=b2
- B2_BUCKET=my-backup-bucket
- B2_KEY_ID=${B2_KEY_ID}
- B2_APPLICATION_KEY=${B2_APP_KEY}
```

**Google Drive**:
```yaml
- CLOUD_PROVIDER=gdrive
- GDRIVE_FOLDER_ID=folder-id
```

### Notification Services
Send alerts on backup success/failure:
```yaml
- NOTIFICATION_ENABLED=true
- NOTIFICATION_TYPE=discord  # discord, slack, email, pushover
- DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK}
```

## Troubleshooting

### Backup Not Running
1. Check logs: `docker logs lazywarden`
2. Verify cron schedule is correct
3. Check container is running: `docker ps`
4. Test manual backup: `docker exec lazywarden /app/backup.sh`
5. Verify permissions on backup directory

### Permission Denied Errors
```
ERROR: Cannot read Vaultwarden data
```

**Fix**: Ensure Vaultwarden data is mounted and readable:
```yaml
volumes:
  - ../bitwarden/data:/vaultwarden-data:ro
```

### Encryption Errors
```
ERROR: Encryption failed
```

**Fix**:
1. Verify BACKUP_ENCRYPTION_PASSWORD is set
2. Check password doesn't contain special shell characters
3. Test encryption manually

### Disk Space Full
```
ERROR: No space left on device
```

**Fix**:
1. Check disk space: `df -h`
2. Reduce BACKUP_RETENTION_DAYS
3. Move backups to larger drive
4. Enable cloud upload and reduce local retention

### Cloud Upload Fails
1. Verify cloud credentials are correct
2. Check network connectivity
3. Verify bucket/folder exists
4. Review cloud provider API logs

## Best Practices

1. **Encryption**: Always encrypt backups (contain passwords)
2. **Retention**: Keep 30-90 days of backups
3. **Offsite Backups**: Upload to cloud for disaster recovery
4. **Test Restores**: Periodically test backup restoration
5. **Monitor**: Set up notifications for backup failures
6. **Separate Storage**: Store backups on different disk than Vaultwarden
7. **3-2-1 Rule**: 3 copies, 2 different media, 1 offsite

## Security Considerations

- **Encryption Password**: Strong password, store securely
- **Cloud Credentials**: Protect API keys and tokens
- **Read-Only Mount**: Vaultwarden data mounted read-only
- **Backup Access**: Restrict access to backup directory
- **Network**: No exposed ports (internal service only)
- **Notifications**: Don't include sensitive data in alerts

## Advanced Configuration

### Backup Multiple Vaultwarden Instances
```yaml
services:
  lazywarden-primary:
    volumes:
      - ../bitwarden/data:/vaultwarden-data:ro
      - ./backups-primary:/backups
  
  lazywarden-secondary:
    volumes:
      - ../bitwarden-2/data:/vaultwarden-data:ro
      - ./backups-secondary:/backups
```

### Custom Backup Script
Mount custom pre/post backup scripts:
```yaml
volumes:
  - ./scripts/pre-backup.sh:/app/hooks/pre-backup.sh:ro
  - ./scripts/post-backup.sh:/app/hooks/post-backup.sh:ro
```

### Webhook Notifications
```yaml
- NOTIFICATION_TYPE=webhook
- WEBHOOK_URL=https://your-webhook-url.com
- WEBHOOK_METHOD=POST
```

Payload includes backup status, filename, size.

### Backup Verification
Enable integrity checks:
```yaml
- VERIFY_BACKUPS=true
```

Verifies backup files after creation.

### Differential Backups
Some implementations support:
```yaml
- BACKUP_TYPE=differential  # vs full
```

Reduces backup size and time.

## Monitoring

### Check Last Backup
```powershell
Get-ChildItem E:\Docker\lazywarden\data | 
  Sort-Object LastWriteTime -Descending | 
  Select-Object -First 1
```

### Backup Size Tracking
```powershell
Get-ChildItem E:\Docker\lazywarden\data -Filter "*.tar.gz*" | 
  Measure-Object -Property Length -Sum | 
  Select-Object @{Name="TotalSizeMB";Expression={[math]::Round($_.Sum/1MB,2)}}
```

### Logs
```powershell
docker logs -f lazywarden
```

Look for:
- `[INFO] Backup started`
- `[INFO] Backup completed successfully`
- `[INFO] Uploaded to cloud`
- `[ERROR]` - Any errors

### Health Check
No built-in health endpoint. Monitor via:
- Recent backup file exists
- Logs show successful completion
- No ERROR messages in logs

## Backup Contents

Typical Vaultwarden backup includes:
- **db.sqlite3** - Main database (or PostgreSQL dump)
- **attachments/** - File attachments
- **sends/** - Encrypted sends
- **config.json** - Vaultwarden configuration
- **rsa_key.pem** - Encryption keys

## Restore Procedures

### Full Restore
1. Stop Vaultwarden
2. Decrypt backup (if encrypted)
3. Extract backup to data directory
4. Verify file ownership/permissions
5. Start Vaultwarden
6. Test login and data access

### Selective Restore
To restore specific items:
1. Extract backup to temporary location
2. Copy specific files to Vaultwarden data
3. Restart Vaultwarden

### Database-Only Restore
```powershell
# Extract just the database
tar -xzf backup.tar.gz db.sqlite3
# Copy to Vaultwarden
Copy-Item db.sqlite3 E:\Docker\bitwarden\data\
```

## Backup Testing

### Test Restoration Monthly
```powershell
# 1. Create test restore directory
mkdir E:\Temp\vault-restore-test

# 2. Extract latest backup
$Latest = Get-ChildItem E:\Docker\lazywarden\data | Sort-Object LastWriteTime -Descending | Select-Object -First 1
tar -xzf $Latest.FullName -C E:\Temp\vault-restore-test\

# 3. Verify files
Get-ChildItem E:\Temp\vault-restore-test -Recurse

# 4. Cleanup
Remove-Item -Recurse -Force E:\Temp\vault-restore-test
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| BACKUP_SCHEDULE | 0 2 * * * | Cron schedule for backups |
| BACKUP_RETENTION_DAYS | 30 | Days to keep backups |
| BACKUP_ENCRYPTION | false | Enable backup encryption |
| BACKUP_ENCRYPTION_PASSWORD | - | Encryption password |
| VAULTWARDEN_DATA | /vaultwarden-data | Path to Vaultwarden data |
| BACKUP_DIR | /backups | Backup storage location |
| UPLOAD_TO_CLOUD | false | Enable cloud upload |
| CLOUD_PROVIDER | - | s3, b2, gdrive |
| NOTIFICATION_ENABLED | false | Enable notifications |
| NOTIFICATION_TYPE | - | discord, slack, email, webhook |
| VERIFY_BACKUPS | false | Verify backup integrity |
| TZ | UTC | Timezone for scheduling |

## Automation Script

### Automated Backup Verification
```powershell
# verify-lazywarden-backup.ps1
$BackupDir = "E:\Docker\lazywarden\data"
$MaxAge = 2  # Days

$LatestBackup = Get-ChildItem $BackupDir | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($null -eq $LatestBackup) {
    Write-Error "No backups found!"
    exit 1
}

$Age = (Get-Date) - $LatestBackup.LastWriteTime

if ($Age.TotalDays -gt $MaxAge) {
    Write-Error "Latest backup is $($Age.TotalDays) days old! (Max: $MaxAge)"
    exit 1
}

Write-Host "✓ Latest backup: $($LatestBackup.Name) ($([math]::Round($Age.TotalHours,1)) hours old)"
```

Schedule to run daily for monitoring.

This automated backup solution ensures Vaultwarden password vault data is protected with scheduled backups, encryption, retention policies, and optional cloud storage for disaster recovery.
