# GitOps Quick Reference

Quick commands and examples for common GitOps operations.

## Common Commands

### Deploy a Service Automatically
```bash
# Make changes to a service
cd plex
vim docker-compose.yml

# Commit and push (creates PR or commits to branch)
git add docker-compose.yml
git commit -m "Update Plex configuration"
git push

# Merge PR to main → Automatic deployment!
```

### Manual Deployment via GitHub Actions
1. Go to: https://github.com/Rubiss/docker/actions/workflows/deploy.yml
2. Click "Run workflow"
3. Enter service name: `plex` or `pi/homebridge`
4. Click "Run workflow"

### Deploy from Local Host
```bash
# On Windows server (via WSL)
cd /mnt/e/Docker
./scripts/deploy-service.sh plex

# On Raspberry Pi
cd /home/rubiss/docker
./scripts/deploy-service.sh homebridge
```

## Service Naming

### Windows Services (Root Directory)
- `plex` - Plex Media Server
- `sonarr` - TV show management
- `radarr` - Movie management
- `bitwarden` - Password manager
- `homepage` - Dashboard
- `grafana` - Metrics visualization
- etc.

### Raspberry Pi Services (pi/ Directory)
- `homebridge` (use just name, not `pi/homebridge` in script)
- `pi-hole`
- `watchtower`
- `cadvisor`
- `node-exporter`

## Workflow Triggers

### Automatic Deployment
These file changes trigger automatic deployment when merged to main:
- `<service>/docker-compose.yml`
- `<service>/.env`
- `pi/<service>/docker-compose.yml`
- `pi/<service>/.env`

### No Automatic Deployment
These changes do NOT trigger deployment:
- `<service>/config/**` - Config files
- `<service>/data/**` - Data files
- `README.md` - Documentation
- `.github/instructions/**` - Instructions

For these, use manual deployment.

## Deployment Process

Each deployment follows these steps:
1. SSH to appropriate host (Windows or Pi)
2. `cd /path/to/service`
3. `git pull origin main`
4. `docker compose pull`
5. `docker compose up -d`
6. `docker compose ps` (show status)

## Monitoring Deployments

### View in GitHub
https://github.com/Rubiss/docker/actions

### View Service Status
```bash
# On host
docker compose ps
docker compose logs --tail=50
docker compose logs -f  # Follow logs
```

### Check Last Deployment
```bash
# On host
cd /path/to/service
git log -1  # Last commit
docker compose ps  # Service status
```

## Rollback

### Automatic via Git Revert
```bash
# Find problematic commit
git log

# Revert it
git revert <commit-hash>
git push origin main

# Workflow automatically redeploys previous version
```

### Manual Rollback
```bash
# On host
cd /path/to/service
git checkout <previous-commit> -- docker-compose.yml
docker compose up -d
```

## Troubleshooting

### Check Workflow Status
- Go to Actions tab
- Click failed workflow
- Review logs for each step
- Check SSH connection, git pull, docker commands

### Test SSH Connectivity
```bash
# From development machine
ssh -i ~/.ssh/github_actions_windows user@windows-host "docker --version"
ssh -i ~/.ssh/github_actions_pi rubiss@pi-host "docker --version"
```

### Verify Service Configuration
```bash
# On host
cd /path/to/service
docker compose config  # Validate syntax
docker compose pull    # Test image pull
docker compose up -d   # Test restart
```

## Advanced Usage

### Deploy Multiple Services
Change multiple services, commit all at once:
```bash
cd /repo/root
# Make changes to multiple services
git add plex/docker-compose.yml sonarr/.env radarr/docker-compose.yml
git commit -m "Update media stack configuration"
git push
# Merging to main deploys all 3 services in parallel
```

### Emergency Stop
```bash
# Stop workflow in GitHub Actions UI
# Or SSH to host and stop service
ssh user@host
docker compose stop <service>
```

### View All Deployments
```bash
# GitHub Actions history
https://github.com/Rubiss/docker/actions/workflows/deploy.yml

# Git history
git log --oneline --graph --all
```

## Best Practices

1. **Test Locally First**
   ```bash
   docker compose config  # Validate
   docker compose up -d   # Test
   docker compose logs    # Check logs
   ```

2. **Small Changes**
   - One service per commit (usually)
   - Clear commit messages
   - Review PR before merging

3. **Monitor Deployments**
   - Watch Actions tab during deployment
   - Check service logs after deployment
   - Verify service is running correctly

4. **Use PRs**
   - Create branch for changes
   - Open PR for review
   - Merge to main when ready
   - Automatic deployment happens on merge

## Links

- [Full Documentation](./GITOPS.md)
- [GitHub Actions](https://github.com/Rubiss/docker/actions)
- [Repository](https://github.com/Rubiss/docker)
