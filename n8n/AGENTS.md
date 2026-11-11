# n8n Workflow Automation

## Service Overview
n8n is a fair-code licensed workflow automation tool that allows you to connect various services and automate tasks through visual workflows.

## Container Configuration
- **Image**: `n8nio/n8n:<stable-version>@sha256:<digest>` (publisher's direct Docker Hub repository; weekly Dependabot checks previously failed with HTTP 429 through `docker.n8n.io`)
- **Container Name**: `n8n`
- **Port**: `5678:5678`
- **Network**: `proxynet`

## Volume Mounts
```
./config:/home/node/.n8n    # n8n configuration and workflows
./workflows:/files          # Auto-import directory for JSON workflows
```

## Native workflows and recovery

The only retained workflow is Sunday Edge worker autoscaling. Native startup
uses the admitted wrapper and exact published workflow identity; it does not
import or activate every export. Preserve its encrypted SSH credential and
existing n8n database. Workflow changes need deliberate admission.

The owner retired the former Uptime Kuma-triggered container restarts,
Transmission watchdog, IRC recovery loops and automatic torrent cleanup.
Docker's `unless-stopped` policy handles exited containers. An unhealthy check
alone does not cause an automatic restart; failures use existing Grafana
notification channels. Inspect the affected service before intervening.
Never remove torrent registrations or data without the owner's immediate,
specific approval. Git history retains the retired automation if needed later.

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
cd /srv/Docker
python3 scripts/native-deploy/compose.py --stack n8n -- restart n8n
```

## Integration with Other Services
n8n can connect to all services in this infrastructure:
- **Plex**: Automate media library management
- **Bitwarden**: Password management automation

## Sunday Edge autoscaling

`workflows/sunday-edge-autoscale-workflow.json` runs every 30 seconds using the
encrypted `sundayEdgeHostSsh` SSH credential. The fixed
`sunday-edge-autoscale-native` command invokes the installed root-controlled native
controller, whose source is `scripts/sunday-edge-autoscale.py`. It shares the
native deployment lock and routes Compose operations through native admission;
overlapping executions skip safely. The result node converts a nonzero SSH exit
into a failed workflow execution. See `sunday-edge/AGENTS.md` for limits, drains,
pause, source promotion and validation. No new Docker API privileges are granted.

The dedicated `sshPrivateKey` stays in n8n's encrypted credential store. Preserve
the native SSH account's existing `restrict,command="/usr/local/sbin/n8n-sunday-autoscale-ssh-entry"`
key restriction and exact sudoers commands. The entry point permits only the fixed
controller command and its dry run, including the SSH node's literal `cd '.' ;`
prefix. Other commands and forwarding must be refused. Its two shell sources are
in `scripts/native-sunday-edge/`; no Windows OpenSSH or PowerShell wrapper remains.
The workflow invokes the restricted host controller over SSH. n8n has no Docker
proxy attachment or writable autobrr/cross-seed mount. Its workflow export is
read-only; application writes stay in its existing configuration directory.

## Security Notes

- Credentials are encrypted in the database
- Use environment variables for sensitive data
- Configure webhook authentication for external triggers
- Enable 2FA for production deployments

## Troubleshooting

### Workflows Not Saving
Check file permissions in `./config`

### Webhook Issues
Verify `WEBHOOK_URL` matches your public domain and SWAG reverse proxy configuration

### Connection Errors to Other Services
Ensure services are on the same `proxynet` network
