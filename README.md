# Docker Home Lab

Docker Compose configurations for a self-hosted home lab across a main Docker host and Raspberry Pi services.

## Infrastructure

This repository contains Docker configurations for:

- **Main Docker host**: Media services, infrastructure services, gaming servers, and observability tooling.
- **Raspberry Pi services**: Lightweight services under `pi/`, including Homebridge, Pi-hole, Glances, cAdvisor, node-exporter, Speedtest Tracker, and Cloudflare Tunnel.

## Repository Layout

- Root service directories contain independent Docker Compose stacks for the main host.
- `pi/<service>/` directories contain independent Docker Compose stacks for Raspberry Pi services.
- Service-specific instructions live in the nearest `AGENTS.md` file.
- New service setup and repository-wide conventions are documented in [AGENTS.md](./AGENTS.md).

## Quick Links

- [Repository guidance](./AGENTS.md)
- [Main deploy workflow](./.github/workflows/deploy-service-changes.yml)
- [PR validation workflow](./.github/workflows/pr-validation.yml)
- [Dependabot configuration](./.github/dependabot.yml)

## Secret Management

This repository uses public non-secret defaults plus git-crypt encrypted secret overlays.

### Public Files

The following files are intended to be tracked in plain text and must not contain secrets:

- `.env`
- `db.env`
- `.env.example`
- `db.env.example`

These files contain non-secret defaults such as ports, usernames, container settings, paths, and feature flags that should be visible to GitHub automation.

### Encrypted Files

The encrypted file patterns are defined in [.gitattributes](./.gitattributes). Current git-crypt protected patterns are:

- `*.env.secret`
- `openclaw/config/*.json`
- `openclaw/config/agents/**/auth-profiles.json`
- `openclaw/config/agents/**/models.json`
- `**/secrets.yml`
- `swag/config/dns-conf/*.ini`

Most services load `.env` first and then `.env.secret` as an optional overlay. Database-backed services may also use `db.env` plus `db.env.secret`.

### Setup for Private Deployments

To unlock encrypted files on a trusted machine:

```bash
sudo apt-get install git-crypt
git-crypt unlock /path/to/git-crypt-key
```

If you do not have the git-crypt key, the public `.env` files are still available, but encrypted secret overlays cannot be decrypted. Create your own `.env.secret` or `db.env.secret` files locally for deployment.

## GitHub Automation

Pull requests run a GitHub-hosted validation workflow before merge. Deployment runs only after trusted pushes to `main` and is guarded so self-hosted runners are not used for pull request code.

The Ubuntu runner uses a [dedicated Docker CLI configuration](scripts/runner-docker-auth.md) for public-image pulls so deployments do not depend on an interactive Windows credential session. Preserve that service configuration across WSL maintenance and reconcile interrupted deployments after Docker is healthy.
