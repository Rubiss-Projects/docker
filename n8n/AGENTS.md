# n8n Workflow Automation

## Service Overview
n8n is a fair-code licensed workflow automation tool that allows you to connect various services and automate tasks through visual workflows.

## Container Configuration
- **Image**: `docker.n8n.io/n8nio/n8n`
- **Container Name**: `n8n`
- **Port**: `5678:5678`
- **Network**: `proxynet`

## Volume Mounts
```
./config:/home/node/.n8n    # n8n configuration and workflows
./workflows:/files          # Auto-import directory for JSON workflows
```

## Workflow Management (Auto-Import)
This service is configured to automatically import and activate workflows from the filesystem on startup.

1.  **Location**: Place your workflow JSON files in `./workflows`.
2.  **Mechanism**: A custom startup script (`import-workflows.sh`) runs when the container starts.
3.  **Behavior**:
    *   Scans `/files/*.json` (mapped to `workflows` folder).
    *   Imports the workflow using `n8n import:workflow`.
    *   Extracts the ID and activates the workflow using `n8n update:workflow`.
    *   Starts the main n8n process.
4.  **To Apply Changes**: Simply restart the container:
    ```bash
    docker compose restart n8n
    ```

## Environment Variables
- `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true` - Enforce file permission checks
- `N8N_HOST=${SUBDOMAIN}.${DOMAIN_NAME}` - Public hostname for n8n
- `N8N_PORT=5678` - Internal port
- `N8N_PROTOCOL=https` - Protocol for external access
- `N8N_RUNNERS_ENABLED=true` - Enable workflow runners
- `NODE_ENV=production` - Node environment
- `WEBHOOK_URL=https://${SUBDOMAIN}.${DOMAIN_NAME}/` - Webhook base URL
- `GENERIC_TIMEZONE` - Timezone for n8n
- `TZ` - System timezone

## Access
- **Local**: http://localhost:5678
- **External**: https://${SUBDOMAIN}.${DOMAIN_NAME} (via SWAG reverse proxy)

## Key Features
- Visual workflow builder
- 400+ integrations
- Webhook support
- Custom code nodes (JavaScript/Python)
- Error handling and retries
- Scheduling and triggers
- Credential management

## Common Operations

### Access Workflows
Navigate to http://localhost:5678 to access the n8n interface

### Backup Workflows
Workflows are stored in `./config` and can be exported/imported via the UI

### View Logs
```bash
docker logs n8n
```

### Restart Service
```bash
cd /mnt/e/Docker/n8n
docker compose restart
```

## Integration with Other Services
n8n can connect to all services in this infrastructure:
- **Ollama**: Use HTTP Request nodes to call http://ollama:11434/api endpoints
- **Plex**: Automate media library management
- **Bitwarden**: Password management automation
- **Actual Budget**: Financial workflow automation

## autobrr IRC Recovery

- `irc-recovery-policies.json` is git-crypt protected because provider names, nicks, auth modes, and secret-key mappings are private.
- `scripts/autobrr_irc_recovery.js` performs provider-specific recovery from Grafana alerts.
- `scripts/autobrr_irc_watchdog.js` is the scheduled missed-alert fallback.
- Recovery credentials and the recovery API key live only in git-crypt protected `irc-recovery-secrets.json`. This file is intentionally separate from Compose dotenv files so `$` and other password characters are never interpolated by Compose.

## Security Notes
- Credentials are encrypted in the database
- Use environment variables for sensitive data
- Configure webhook authentication for external triggers
- Enable 2FA for production deployments

## Remediation coordination

`self_heal_container.js` acquires an atomic per-container lease under `config/self-heal-locks/<container>/lease.json` before it starts or restarts anything. Other automation, including AI SRE, must treat a fresh lease as authoritative and must not perform a simultaneous remediation for that container. Leases are removed on process exit and may be reclaimed after five minutes if a process is interrupted.

## Troubleshooting

### Workflows Not Saving
Check file permissions in `./config`

### Webhook Issues
Verify `WEBHOOK_URL` matches your public domain and SWAG reverse proxy configuration

### Connection Errors to Other Services
Ensure services are on the same `proxynet` network
