# GitOps Automated Deployment

> **Quick Reference**: See [GITOPS-QUICKREF.md](./GITOPS-QUICKREF.md) for common commands and examples.

This repository implements automated GitOps deployment using GitHub Actions. When changes are merged to the `main` branch, affected services are automatically deployed to the appropriate host (Windows server or Raspberry Pi).

## Overview

### How It Works

1. **Change Detection**: When a PR is merged to `main`, the workflow detects which services changed by analyzing modified `docker-compose.yml` or `.env` files
2. **Parallel Deployment**: Changed services are deployed in parallel (up to 5 at a time) for faster deployments
3. **Automatic Routing**: Services are automatically deployed to the correct host:
   - Services in `pi/` directory → Raspberry Pi
   - All other services → Windows Docker host
4. **Safe Restart**: Each service is updated via:
   - `git pull` - Get latest configuration
   - `docker compose pull` - Pull latest images
   - `docker compose up -d` - Restart with new config

### Workflow Features

- ✅ Automatic change detection
- ✅ Parallel deployment of independent services
- ✅ Support for both Windows and Raspberry Pi hosts
- ✅ Manual deployment trigger for specific services
- ✅ Deployment status summaries
- ✅ git-crypt compatible (encrypted secrets remain encrypted)
- ✅ Rollback via git revert

## Initial Setup

### Prerequisites

Both deployment hosts (Windows server and Raspberry Pi) must have:
- Git installed and repository cloned
- Docker and Docker Compose installed
- SSH server running and accessible
- git-crypt unlocked (for encrypted .env files)

### Step 1: Generate SSH Keys

Generate SSH key pairs for GitHub Actions to access your hosts:

```bash
# For Windows host
ssh-keygen -t ed25519 -f ~/.ssh/github_actions_windows -C "github-actions-windows"

# For Raspberry Pi
ssh-keygen -t ed25519 -f ~/.ssh/github_actions_pi -C "github-actions-pi"
```

### Step 2: Add Public Keys to Hosts

**On Windows Server (via WSL or PowerShell):**
```bash
# Add the public key to authorized_keys
cat ~/.ssh/github_actions_windows.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

**On Raspberry Pi:**
```bash
# Add the public key to authorized_keys
cat ~/.ssh/github_actions_pi.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### Step 3: Configure GitHub Secrets

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions):

#### Windows Host Secrets
- `WINDOWS_SSH_KEY`: Contents of `~/.ssh/github_actions_windows` (private key)
- `WINDOWS_HOST`: IP address or hostname of Windows server
- `WINDOWS_SSH_USER`: SSH username (e.g., `ben` or your WSL user)
- `WINDOWS_SSH_PORT`: SSH port (default: `22`)

#### Raspberry Pi Secrets
- `PI_SSH_KEY`: Contents of `~/.ssh/github_actions_pi` (private key)
- `PI_HOST`: IP address of Raspberry Pi (e.g., `192.168.50.216`)
- `PI_SSH_USER`: SSH username (e.g., `rubiss`)
- `PI_SSH_PORT`: SSH port (default: `22`)

### Step 4: Ensure Repository is Cloned on Hosts

**On Windows Server (WSL):**
```bash
cd /mnt/e/Docker
git pull origin main
```

**On Raspberry Pi:**
```bash
cd /home/rubiss/docker
git pull origin main
```

### Step 5: Test SSH Connectivity

From your development machine, test SSH access:

```bash
# Test Windows host
ssh -i ~/.ssh/github_actions_windows user@windows-host "docker --version"

# Test Raspberry Pi
ssh -i ~/.ssh/github_actions_pi rubiss@pi-host "docker --version"
```

## Usage

### Automatic Deployment

When you merge a PR to `main`, the workflow automatically:
1. Detects which services changed
2. Deploys them to the appropriate hosts
3. Shows deployment status in the Actions tab

### Manual Deployment

Deploy a specific service manually:

1. Go to **Actions** → **Deploy Services**
2. Click **Run workflow**
3. Enter the service name (e.g., `plex`, `sonarr`, or `pi/homebridge`)
4. Click **Run workflow**

### Using the Deployment Script Locally

You can also use the deployment script directly on the hosts:

```bash
# On Windows or Pi host
cd /mnt/e/Docker  # or /home/rubiss/docker for Pi
./scripts/deploy-service.sh <service-name>

# Examples:
./scripts/deploy-service.sh plex
./scripts/deploy-service.sh sonarr
./scripts/deploy-service.sh homebridge  # Automatically detects Pi service
```

## Workflow Details

### File: `.github/workflows/deploy.yml`

The workflow consists of three jobs:

1. **detect-changes**: Analyzes git diff to find changed services
2. **deploy-windows-services**: Deploys services in parallel via SSH
3. **notify**: Creates a deployment summary

### Supported File Changes

The workflow triggers deployment when these files change:
- `<service>/docker-compose.yml` - Service configuration
- `<service>/.env` - Environment variables
- `pi/<service>/docker-compose.yml` - Pi service configuration
- `pi/<service>/.env` - Pi environment variables

### Change Detection Logic

```bash
# Detects changes in service directories
git diff --name-only | grep -E '^[^/]+/(docker-compose\.yml|\.env)$'
```

Only top-level changes trigger deployment. Subdirectory changes (like `config/`, `data/`) do not trigger automatic deployment.

## Security Considerations

### SSH Key Management

- Private keys are stored as GitHub Secrets (encrypted at rest)
- Keys are only exposed to GitHub Actions runners during workflow execution
- Use separate SSH keys for different hosts
- Rotate keys periodically

### git-crypt and Secrets

- `.env` files remain encrypted in the repository (git-crypt)
- Hosts must have git-crypt unlocked to read encrypted files
- GitHub Actions workflow never decrypts secrets
- Deployment happens on the host where secrets are already decrypted

### Network Security

- Ensure SSH is properly secured (key-based auth only, firewall rules)
- Consider using SSH bastions or VPN for additional security
- Limit SSH access to specific IP ranges if possible

## Troubleshooting

### Deployment Fails with "Connection Refused"

**Cause**: SSH cannot connect to host
**Solution**: 
- Check host is online: `ping <host>`
- Verify SSH service is running
- Check firewall allows SSH port
- Verify SSH key is correct in GitHub Secrets

### Deployment Fails with "Permission Denied"

**Cause**: SSH key not authorized on host
**Solution**:
- Verify public key is in `~/.ssh/authorized_keys` on host
- Check file permissions: `chmod 600 ~/.ssh/authorized_keys`
- Ensure private key in GitHub Secrets matches public key on host

### Service Doesn't Restart

**Cause**: Docker Compose error or missing dependencies
**Solution**:
- SSH to host and check logs: `docker compose logs`
- Verify docker-compose.yml syntax
- Check Docker daemon is running: `docker ps`

### Changes Not Detected

**Cause**: Files changed are not in service root directory
**Solution**:
- Only changes to `<service>/docker-compose.yml` or `<service>/.env` trigger deployment
- Config file changes don't auto-deploy (by design)
- Use manual deployment for these cases

### git-crypt Not Working

**Cause**: Repository not unlocked on host
**Solution**:
- SSH to host
- Run `git-crypt unlock /path/to/key`
- Verify with `git-crypt status`

## Advanced Configuration

### Customizing Deployment Behavior

Edit `.github/workflows/deploy.yml` to customize:

- **Parallel deployments**: Change `max-parallel: 5` in the matrix
- **Deployment strategy**: Change `fail-fast: false` to stop on first failure
- **Additional steps**: Add post-deployment health checks, notifications, etc.

### Adding Deployment Notifications

Add a notification step to send deployment status to Discord/Slack:

```yaml
- name: Notify Discord
  if: always()
  uses: sarisia/actions-status-discord@v1
  with:
    webhook: ${{ secrets.DISCORD_WEBHOOK }}
    status: ${{ job.status }}
    title: "Deployment: ${{ matrix.service }}"
```

### Pre-deployment Validation

Add validation steps before deployment:

```yaml
- name: Validate docker-compose.yml
  run: |
    cd ${{ matrix.service }}
    docker compose config --quiet
```

## Rollback Procedure

If a deployment causes issues, rollback to previous version:

1. **Identify the problematic commit**: Check GitHub Actions history
2. **Revert the commit**: 
   ```bash
   git revert <commit-hash>
   git push origin main
   ```
3. **Automatic redeployment**: The workflow will automatically deploy the reverted version

## Best Practices

1. **Test changes locally first**: Always test docker-compose changes locally before pushing
2. **Use PRs for changes**: Review changes before merging to main
3. **Monitor deployments**: Watch the Actions tab during deployments
4. **Keep services isolated**: Each service in its own directory enables independent deployment
5. **Document service dependencies**: If services depend on each other, coordinate deployments
6. **Regular key rotation**: Rotate SSH keys every 6-12 months
7. **Backup before major changes**: Take backups before deploying major service updates

## Monitoring Deployments

### GitHub Actions UI

View deployment status:
1. Go to **Actions** tab in GitHub
2. Click on **Deploy Services** workflow
3. View individual service deployment logs

### Deployment Summary

After each deployment, check the workflow summary for:
- List of deployed services
- Deployment status (success/failure)
- Commit hash and author

### Service Health Checks

After deployment, verify services are running:

```bash
# On host
docker compose ps
docker compose logs --tail=50
```

## Future Enhancements

Potential improvements to consider:

- [ ] Blue-green deployments for zero-downtime
- [ ] Automated health checks post-deployment
- [ ] Deployment approvals for production services
- [ ] Integration with monitoring systems (Uptime Kuma)
- [ ] Automated rollback on health check failure
- [ ] Deployment metrics and dashboards
- [ ] Multi-environment support (dev/staging/prod)

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review workflow logs in GitHub Actions
3. Check service logs on the deployment host
4. Refer to service-specific instructions in `.github/instructions/`
