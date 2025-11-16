---
applyTo: 'n8n/**'
---

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
E:\Docker\n8n\config:/home/node/.n8n    # n8n configuration and workflows
E:\Docker\n8n\data:/files                # File storage for workflows
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
- **External**: https://${SUBDOMAIN}.${DOMAIN_NAME} (via Nginx Proxy Manager)

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
Workflows are stored in `E:\Docker\n8n\config` and can be exported/imported via the UI

### View Logs
```bash
docker logs n8n
```

### Restart Service
```bash
cd E:\Docker\n8n
docker compose restart
```

## Integration with Other Services
n8n can connect to all services in this infrastructure:
- **Ollama**: Use HTTP Request nodes to call http://ollama:11434/api endpoints
- **Plex**: Automate media library management
- **Bitwarden**: Password management automation
- **Actual Budget**: Financial workflow automation

## Security Notes
- Credentials are encrypted in the database
- Use environment variables for sensitive data
- Configure webhook authentication for external triggers
- Enable 2FA for production deployments

## Troubleshooting

### Workflows Not Saving
Check file permissions in `E:\Docker\n8n\config`

### Webhook Issues
Verify `WEBHOOK_URL` matches your public domain and Nginx Proxy Manager configuration

### Connection Errors to Other Services
Ensure services are on the same `proxynet` network
