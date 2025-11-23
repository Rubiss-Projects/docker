---
applyTo: "bitwarden/**"
---

# Bitwarden (Vaultwarden) Expert Instructions

You are an expert in Vaultwarden, the lightweight Bitwarden-compatible password manager server.

## Service Overview
Vaultwarden is an alternative implementation of the Bitwarden server API, optimized for self-hosted deployments. It's fully compatible with official Bitwarden clients while using significantly fewer resources.

## Technical Configuration

### Docker Compose Patterns
```yaml
# Vaultwarden with PostgreSQL database
services:
  bitwarden:
    image: vaultwarden/server:latest
    ports:
      - "8080:80"
    volumes:
      - ./data:/data
    environment:
      - DATABASE_URL=postgresql://bitwarden:${DB_PASSWORD}@db:5432/bitwarden
      - ADMIN_TOKEN=${ADMIN_TOKEN}
      - SIGNUPS_ALLOWED=false  # Disable after creating accounts
      - INVITATIONS_ALLOWED=true
      - DOMAIN=https://bitwarden.benlawson.dev
      - SMTP_HOST=smtp.gmail.com
      - SMTP_FROM=${SMTP_FROM}
      - SMTP_PORT=587
      - SMTP_SECURITY=starttls
      - SMTP_USERNAME=${SMTP_USERNAME}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
    depends_on:
      - db
    networks:
      - proxynet
    restart: unless-stopped

  db:
    image: postgres:15
    volumes:
      - ./db-data:/var/lib/postgresql/data
    env_file:
      - db.env  # Contains POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_USER
    networks:
      - proxynet
    restart: unless-stopped
```

### Critical Files
- `data/` - Vaultwarden data (attachments, icons, etc.)
- `data/db.sqlite3` - SQLite database (if not using PostgreSQL)
- `db-data/` - PostgreSQL database files
- `db.env` - Database credentials (DO NOT COMMIT)

### Environment Variables

**Required:**
- `DATABASE_URL` - PostgreSQL connection string
- `ADMIN_TOKEN` - Admin panel password (generate with `openssl rand -base64 48`)
- `DOMAIN` - Your Bitwarden URL (for email links)

**Recommended:**
- `SIGNUPS_ALLOWED=false` - Disable after creating accounts
- `INVITATIONS_ALLOWED=true` - Allow existing users to invite
- `SMTP_*` - Email configuration for invitations and password resets

## Common Tasks

### First-Time Setup
1. Generate admin token:
```powershell
# PowerShell
$bytes = New-Object Byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes)
```

2. Add to docker-compose.yml or .env:
```
ADMIN_TOKEN=generated_token_here
```

3. Start services:
```powershell
docker compose up -d
```

4. Access admin panel: `https://bitwarden.benlawson.dev/admin`
5. Create first user account
6. Disable signups: `SIGNUPS_ALLOWED=false`

### Create User Account
**Via Web Vault:**
1. Go to `https://bitwarden.benlawson.dev`
2. Click "Create Account"
3. Enter email and master password
4. Verify email (if SMTP configured)

**Via Admin Panel:**
1. Go to `/admin`
2. Users > Invite User
3. Enter email address
4. User receives invitation email

### Backup Vaultwarden
```powershell
# Stop services
docker compose stop

# Backup data and database
tar -czf bitwarden-backup-$(Get-Date -Format "yyyyMMdd").tar.gz data/ db-data/

# Start services
docker compose start
```

### Restore from Backup
```powershell
docker compose stop
tar -xzf bitwarden-backup-YYYYMMDD.tar.gz
docker compose start
```

### View Logs
```powershell
docker logs bitwarden -f
docker logs bitwarden-db -f
```

### Access Admin Panel
- URL: `https://bitwarden.benlawson.dev/admin`
- Token: Value of `ADMIN_TOKEN`
- Use for: User management, settings, diagnostics

## Integration Points

### Homepage Dashboard
```yaml
- Bitwarden:
    icon: bitwarden.png
    href: https://bitwarden.benlawson.dev
    description: Password manager
```

### Nginx Proxy Manager
```
Domain: bitwarden.benlawson.dev
Forward: http://bitwarden:80
Websockets: Yes (required for sync)
SSL: Let's Encrypt (force SSL)
Custom Config:
  client_max_body_size 128M;  # For file attachments
```

### Email (SMTP) Configuration
Required for:
- User invitations
- Password reset emails
- Two-factor authentication setup

**Gmail Example:**
```yaml
SMTP_HOST=smtp.gmail.com
SMTP_FROM=your-email@gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=app-specific-password  # Not your Gmail password
```

Get Gmail app password:
1. Google Account > Security > 2-Step Verification
2. App passwords > Generate

### Bitwarden Clients
Compatible with all official clients:
- **Browser Extensions**: Chrome, Firefox, Edge, Safari, Opera
- **Desktop Apps**: Windows, macOS, Linux
- **Mobile Apps**: iOS, Android
- **CLI**: Bitwarden CLI tool

Configuration in clients:
1. Settings > Self-hosted
2. Server URL: `https://bitwarden.benlawson.dev`
3. Log in with email and master password

## Troubleshooting

### Cannot Log In
1. Verify URL is correct in client
2. Check DOMAIN environment variable matches
3. Clear browser cache/cookies
4. Try different browser/client
5. Review Vaultwarden logs: `docker logs bitwarden`

### WebSocket Connection Failed
1. Ensure WebSockets enabled in NPM
2. Check browser console for errors
3. Verify DOMAIN is set correctly
4. Test: Try different browser

### Email Not Sending
1. Verify SMTP settings in docker-compose.yml
2. Test SMTP connection:
```powershell
docker exec bitwarden /vaultwarden test-smtp
```
3. Check SMTP provider (Gmail, SendGrid, etc.)
4. Review Vaultwarden logs for SMTP errors

### Database Connection Error
1. Check PostgreSQL is running: `docker ps`
2. Verify DATABASE_URL is correct
3. Test connection:
```powershell
docker exec bitwarden-db psql -U bitwarden -d bitwarden -c "SELECT 1;"
```
4. Check db.env file for correct credentials

### Two-Factor Authentication Not Working
1. Ensure time is synchronized on server
2. Verify TOTP code is current (30-second window)
3. Try backup codes if available
4. Disable 2FA via admin panel if locked out

## Best Practices

1. **Strong Master Password**: 16+ characters, unique
2. **Regular Backups**: Automate weekly backups
3. **Disable Signups**: After creating accounts
4. **Enable 2FA**: For all accounts (TOTP, YubiKey, etc.)
5. **HTTPS Only**: Always use SSL (via NPM)
6. **Secure ADMIN_TOKEN**: Long, random, secret
7. **Email Verification**: Configure SMTP for security
8. **Update Regularly**: Watchtower keeps Vaultwarden updated
9. **Database Backups**: Separate from data directory
10. **Test Restores**: Verify backups work periodically

## Security Considerations

- **Master Password**: Never stored on server, only client-side
- **Encryption**: End-to-end AES-256 encryption
- **Zero-Knowledge**: Server cannot decrypt vault data
- **HTTPS Required**: For secure transmission
- **Admin Token**: Protect like root password
- **Network Isolation**: Keep on proxynet, expose via NPM only
- **No Public Signups**: Disable SIGNUPS_ALLOWED in production
- **Two-Factor Auth**: Mandatory for sensitive accounts
- **Backup Encryption**: Encrypt backup archives

## Advanced Configuration

### File Attachments
Enable file attachments:
```yaml
environment:
  - ATTACHMENTS_FOLDER=/data/attachments
  - MAX_ATTACHMENT_SIZE=104857600  # 100MB in bytes
```

### Organization Support
Vaultwarden supports Bitwarden Organizations (free):
1. Web Vault > New Organization
2. Add members
3. Share passwords within org
4. No license required

### Yubikey Support
Enable hardware 2FA:
```yaml
environment:
  - YUBICO_CLIENT_ID=your_client_id
  - YUBICO_SECRET_KEY=your_secret_key
```

Get keys from: https://upgrade.yubico.com/getapikey/

### Custom Icons
Cache site icons locally:
```yaml
environment:
  - ICON_CACHE_FOLDER=/data/icon_cache
  - ICON_CACHE_TTL=2592000  # 30 days
```

### Rate Limiting
Prevent brute-force attacks:
```yaml
environment:
  - LOGIN_RATELIMIT_MAX_BURST=10
  - LOGIN_RATELIMIT_SECONDS=60
```

### Database Optimization

**PostgreSQL Tuning:**
Create `db-data/postgresql.conf`:
```
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
```

### Backup Automation Script
```powershell
# backup-bitwarden.ps1
$date = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = "..\..\Backups\Bitwarden"
$composeDir = ".\"

# Stop Vaultwarden (optional, for consistency)
Set-Location $composeDir
docker compose stop bitwarden

# Backup
tar -czf "$backupDir\bitwarden-$date.tar.gz" data/ db-data/

# Start Vaultwarden
docker compose start bitwarden

# Keep only last 30 days of backups
Get-ChildItem $backupDir -Filter "bitwarden-*.tar.gz" | 
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | 
  Remove-Item
```

Schedule with Task Scheduler: Daily at 3 AM

## Monitoring and Maintenance

### Check Server Status
Admin Panel > Diagnostics:
- Server version
- Database connection
- WebSocket status
- SMTP status

### User Management
Admin Panel > Users:
- View all users
- Disable/enable users
- Delete users
- Resend invitations

### Database Maintenance
```powershell
# PostgreSQL vacuum (cleanup)
docker exec bitwarden-db vacuumdb -U bitwarden -d bitwarden -v -z

# Check database size
docker exec bitwarden-db psql -U bitwarden -d bitwarden -c "\l+"
```

### Log Levels
Adjust logging verbosity:
```yaml
environment:
  - LOG_LEVEL=trace  # trace, debug, info, warn, error
  - EXTENDED_LOGGING=true
```

## Common Issues and Solutions

### "Invalid master password"
- Verify caps lock is off
- Check keyboard layout
- Try different browser/client
- Master password is case-sensitive

### Organization sharing not working
- Verify user is invited to organization
- Check user accepted invitation
- Ensure collection access is granted
- Review organization policies

### Attachments failing to upload
- Check MAX_ATTACHMENT_SIZE
- Verify client_max_body_size in NPM (128M)
- Check disk space: `df -h`
- Review Vaultwarden logs

### "Connection refused" error
- Verify container is running: `docker ps`
- Check port 8080 is exposed
- Test: `curl http://localhost:8080`
- Verify NPM proxy configuration

## Migration from Bitwarden Cloud

### Export from Cloud
1. Bitwarden Cloud > Tools > Export Vault
2. Format: JSON or CSV
3. Save file securely

### Import to Vaultwarden
1. Vaultwarden Web Vault > Tools > Import Data
2. Select format (JSON/CSV)
3. Upload file
4. Verify imported data
5. Delete export file

### Update Clients
1. Each client > Settings > Self-hosted
2. Server URL: `https://bitwarden.benlawson.dev`
3. Log out of cloud account
4. Log in to self-hosted

## Performance Considerations

### Resource Usage
- **RAM**: 50-100MB (Vaultwarden) + 200-400MB (PostgreSQL)
- **CPU**: Minimal (<5% average)
- **Disk**: Depends on vault size and attachments

### PostgreSQL vs SQLite
- **SQLite** (default): Simple, no separate container
- **PostgreSQL**: Better for multiple concurrent users, more robust
- **Recommendation**: Use PostgreSQL for production

### Scaling
Vaultwarden handles:
- 100+ concurrent users easily
- Thousands of vault items per user
- GB of attachments (with adequate storage)

This self-hosted password manager provides enterprise-level security with minimal resource usage, perfect for home lab and small team deployments.
