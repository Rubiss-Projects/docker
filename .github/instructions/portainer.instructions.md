---
applyTo: "portainer/**"
---

# Portainer Expert Instructions

You are an expert in Portainer Docker management and container orchestration.

## Service Overview
Portainer is a lightweight management UI for Docker. It provides a graphical interface to manage containers, images, networks, volumes, and Docker Compose stacks across single or multiple Docker environments.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "9000:9000"
  - "9443:9443"  # HTTPS
volumes:
  - ./config:/data
  - /var/run/docker.sock:/var/run/docker.sock
restart: unless-stopped
```

### Critical Files
- `config/portainer.db` - Portainer database
- `config/compose/` - Stored compose files
- `/var/run/docker.sock` - Docker API access (required)

### Default Ports
- 9000 - HTTP UI
- 9443 - HTTPS UI

## Common Tasks

### First-Time Setup
1. Access: `http://localhost:9000` or `https://localhost:9443`
2. Create admin account (first user)
3. Connect to local Docker:
   - Environment: Local
   - Socket: `/var/run/docker.sock`
4. Dashboard shows all containers

### Manage Containers
Containers > Select container:
- Start/Stop/Restart/Kill
- View logs (real-time)
- Inspect configuration
- Access console
- View stats (CPU/RAM/Network)

### Deploy Stack (Compose)
Stacks > Add stack:
1. Name: `my-stack`
2. Build method:
   - Web editor (paste docker-compose.yml)
   - Upload file
   - Git repository
3. Environment variables (optional)
4. Deploy stack

### Manage Images
Images:
- Pull new images
- Remove unused images
- Build from Dockerfile
- Import/export images
- Tag images

### Manage Networks
Networks:
- Create custom networks
- View connected containers
- Remove unused networks

### Manage Volumes
Volumes:
- Create named volumes
- Browse volume contents
- Remove unused volumes
- Backup/restore volumes

## Integration Points

### Docker Socket
Required for Portainer to manage Docker:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

**Security**: Full Docker control, equivalent to root access.

### Homepage Dashboard
```yaml
- Portainer:
    icon: portainer.png
    href: http://localhost:9000
    description: Docker management
    widget:
      type: portainer
      url: http://portainer:9000
      env: 1  # Environment ID (usually 1 for local)
      key: ${PORTAINER_API_KEY}
```

Get API key:
1. User menu > My account
2. Access tokens > Add access token

### Nginx Proxy Manager
```
Domain: portainer.benlawson.dev
Forward: http://portainer:9000
Websockets: Yes
SSL: Let's Encrypt
```

### Remote Docker Hosts
Add remote Docker engines:
1. Environments > Add environment
2. Choose: Docker Standalone
3. API URL: `tcp://remote-host:2375`
4. Or use Portainer Agent on remote host

## Troubleshooting

### Cannot Access UI
1. Check container is running: `docker ps`
2. Verify port 9000/9443 is exposed
3. Test: `curl http://localhost:9000`
4. Check firewall settings

### "Cannot connect to Docker engine"
1. Verify Docker socket is mounted
2. Check Docker is running: `docker ps`
3. Permissions: Socket must be accessible
4. Test: `docker exec portainer ls -l /var/run/docker.sock`

### Stacks Fail to Deploy
1. Review error message in UI
2. Check docker-compose.yml syntax
3. Verify required images exist
4. Check volume paths are correct
5. Review Portainer logs

### Slow Performance
1. Reduce polling frequency (Settings)
2. Limit number of environments
3. Check container resource usage
4. Clear browser cache

## Best Practices

1. **Strong Password**: Secure admin account
2. **Regular Updates**: Keep Portainer current
3. **Access Control**: Use RBAC for multi-user
4. **Audit Logs**: Review user actions
5. **Backup Database**: Backup config directory
6. **HTTPS**: Use port 9443 for SSL
7. **API Keys**: Rotate regularly

## Security Considerations

- **Docker Socket**: Full root access to host
- **Authentication**: Strong admin password
- **HTTPS**: Use 9443 for secure access
- **Network Isolation**: Don't expose publicly without VPN/auth
- **User Permissions**: Use RBAC for teams
- **Audit Logs**: Monitor for suspicious activity
- **API Keys**: Treat as passwords

## Advanced Configuration

### Business Edition Features
Portainer Business (paid) adds:
- Role-Based Access Control (RBAC)
- Authentication via OAuth/LDAP
- Container resource limits
- GitOps deployments
- Security scanning
- Kubernetes support

### Edge Agent
For remote Docker hosts behind firewalls:
1. Deploy Portainer Edge Agent on remote
2. Agent connects to Portainer (outbound only)
3. Manage through Portainer UI
4. No inbound ports required

### Teams and Users
Settings > Users:
- Create teams
- Assign users to teams
- Grant environment access
- Set resource limits

### Webhooks
Stacks > Stack > Webhook:
- Auto-redeploy on webhook trigger
- Integrate with CI/CD pipelines
- GitOps workflows

### Custom Templates
App Templates > Add template:
```json
{
  "type": 1,
  "title": "My App",
  "description": "Custom application",
  "logo": "https://...",
  "image": "myapp:latest",
  "ports": ["8080:8080"]
}
```

One-click deployment from custom templates.

## Monitoring

### Container Stats
Dashboard shows:
- Running/stopped container count
- Image count
- Volume count
- Network count

Per-container stats:
- CPU usage %
- Memory usage MB
- Network I/O
- Block I/O

### Resource Limits
Containers > Container > Duplicate/Edit:
- Set memory limits
- Set CPU shares
- Resource reservations

### Events
Home > Events:
- Container start/stop
- Image pull/remove
- Network create/remove
- Volume operations

## API Usage

### Authentication
```powershell
$body = @{
    username = "admin"
    password = "YourPassword"
} | ConvertTo-Json

$auth = Invoke-RestMethod -Uri "http://localhost:9000/api/auth" -Method Post -Body $body -ContentType "application/json"
$token = $auth.jwt

$headers = @{ "Authorization" = "Bearer $token" }
```

### List Containers
```powershell
Invoke-RestMethod -Uri "http://localhost:9000/api/endpoints/1/docker/containers/json?all=1" -Headers $headers
```

### Start Container
```powershell
Invoke-RestMethod -Uri "http://localhost:9000/api/endpoints/1/docker/containers/container_id/start" -Method Post -Headers $headers
```

### Deploy Stack
```powershell
$stack = @{
    Name = "my-stack"
    StackFileContent = Get-Content "docker-compose.yml" -Raw
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:9000/api/stacks?endpointId=1&type=2&method=string" -Method Post -Headers $headers -Body $stack -ContentType "application/json"
```

## Backup and Restore

### Backup Portainer Data
```powershell
docker compose stop
tar -czf portainer-backup-$(Get-Date -Format "yyyyMMdd").tar.gz config/
docker compose start
```

### Restore
```powershell
docker compose stop
tar -xzf portainer-backup-YYYYMMDD.tar.gz
docker compose start
```

## Common Errors

### "Unauthorized" API errors
- Token expired
- Re-authenticate
- Check API key validity

### Stacks show "ERROR"
- Compose syntax error
- Missing images
- Port conflicts
- Volume path issues

### Cannot remove container/image
- Container is running (stop first)
- Image in use by container
- Force remove if necessary

## Performance Tips

- Reduce refresh intervals (Settings > Features)
- Limit environment count
- Use Portainer Agent for remote hosts (less overhead)
- Clear old audit logs

## Multi-Host Management

### Add Docker Standalone
1. Environments > Add environment
2. Docker Standalone
3. API URL: `tcp://host:2375`
4. Test connection

### Add via Agent
1. Deploy Portainer Agent on remote:
```yaml
services:
  agent:
    image: portainer/agent:latest
    ports:
      - "9001:9001"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /var/lib/docker/volumes:/var/lib/docker/volumes
```

2. Portainer > Add environment > Agent
3. URL: `remote-host:9001`

### Cluster Management
For Docker Swarm or Kubernetes, connect cluster manager node.

This powerful Docker management UI simplifies container orchestration with an intuitive web interface for the entire Docker homelab.
