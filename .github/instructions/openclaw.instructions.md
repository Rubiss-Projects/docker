---
applyTo: 'openclaw/**'
---

# OpenClaw AI Gateway - TrollClaw Bot

## Service Overview

OpenClaw is deployed as **TrollClaw** — a cantankerous swamp troll Discord bot powered by GitHub Copilot models. It connects to Discord and provides AI assistant capabilities via the OpenClaw gateway.

**Identity**: TrollClaw is a chaotic-neutral, sharp-tongued troll who lives under the bridge between servers. Sarcastic and mischievous, it roasts other bots but is friendly to humans.

## Current Configuration

### Model Provider: GitHub Copilot

TrollClaw uses **GitHub Copilot** as its LLM provider via device flow authentication.

| Setting | Value |
|---------|-------|
| Primary Model | `github-copilot/claude-haiku-4.5` |
| Fallback 1 | `github-copilot/claude-sonnet-4.5` |
| Fallback 2 | `github-copilot/gpt-5.2` |
| Provider | `github-copilot` (device flow auth) |

**Available Models** (all via `github-copilot/` prefix):
- `claude-haiku-4.5`, `claude-sonnet-4.5`, `claude-opus-4.5`
- `gpt-5.2`, `gpt-5.2-codex`, `gpt-5-mini`, `gpt-4.1`, `gpt-4o`
- `gemini-3-pro`, `gemini-3-flash`
- `grok-code-fast-1`, `raptor-mini`

### Discord Configuration

| Setting | Value |
|---------|-------|
| Bot Name | @trollclaw |
| Bot ID | `1467341771443798057` |
| Guild ID | `1439620486463098932` |
| Channel ID | `1467343589272195288` |
| Group Policy | `allowlist` (only allowed guilds/channels) |
| DM Policy | `pairing` (requires approval code) |
| Require Mention | `true` |

## Container Setup

### Containers
| Container | Purpose |
|-----------|---------|
| `openclaw-gateway` | Long-running daemon handling Discord connections and AI |
| `openclaw-cli` | Ephemeral container for CLI commands |

### Ports
| Port | Purpose |
|------|---------|
| `18789` | Gateway WebSocket/HTTP |
| `18790` | Bridge (mobile nodes) |

### Networks
| Network | Purpose |
|---------|---------|
| `proxynet` | SWAG reverse proxy, inter-service communication |
| `ollama-net` | Local Ollama access (optional, for local models) |
| `socket-proxy-net` | Docker socket proxy for container monitoring |

### Docker Socket Proxy Integration

The gateway connects to the Docker API via `socket-proxy` for container monitoring:
- **DOCKER_HOST**: `tcp://socket-proxy:2375`
- **Network**: `socket-proxy-net` (external)
- **Access**: Read-only container listing, plus start/stop/restart (inherited from socket-proxy permissions)
- **Use case**: Monitoring Docker services, container status checks, health reporting

The socket-proxy provides filtered Docker API access (no direct socket mount needed).

## File Structure

```
openclaw/
├── docker-compose.yml
├── .env                              # Secrets (git-crypt encrypted)
└── config/
    ├── openclaw.json                 # Main config (agents-only, git-crypt encrypted)
    └── agents/
        └── main/
            └── agent/
                └── auth-profiles.json  # GitHub Copilot token (git-crypt encrypted)
```

**Note**: The config directory was reset to a clean state. OpenClaw will regenerate additional files/directories (workspace/, identity/, logs/, etc.) on first startup.

## Authentication

### GitHub Copilot Device Flow

The bot authenticates with GitHub Copilot using device flow. Tokens are stored in:
- `config/agents/main/agent/auth-profiles.json`

### Device Flow Workaround (Host-Side)

The device flow does NOT work inside the Docker container (headless, no browser). Use this workaround to obtain and inject tokens from the WSL host:

**Step 1: Initiate device flow**
```bash
curl -s -X POST "https://github.com/login/device/code" \
  -H "Accept: application/json" \
  -d "client_id=Iv1.b507a08c87ecfe98&scope="
```
This returns a `user_code` and `verification_uri`.

**Step 2: Authorize**
Go to https://github.com/login/device and enter the `user_code`.

**Step 3: Poll for token**
```bash
curl -s -X POST "https://github.com/login/oauth/access_token" \
  -H "Accept: application/json" \
  -d "client_id=Iv1.b507a08c87ecfe98&device_code=<DEVICE_CODE>&grant_type=urn:ietf:params:oauth:grant-type:device_code"
```
Poll every 5-10 seconds until you get an `access_token` (starts with `ghu_`).

**Step 4: Verify token works**
```bash
curl -s -H "Authorization: token ghu_xxxxx" \
  -H "Accept: application/json" \
  https://api.github.com/copilot_internal/v2/token
```
Should return HTTP 200 with a JWT.

**Step 5: Inject into auth-profiles.json**
```bash
mkdir -p openclaw/config/agents/main/agent
cat > openclaw/config/agents/main/agent/auth-profiles.json << 'EOF'
{
  "version": 1,
  "profiles": {
    "github-copilot:github": {
      "type": "token",
      "provider": "github-copilot",
      "token": "ghu_xxxxx..."
    }
  }
}
EOF
```

### Native Auth (Future)

When OpenClaw fixes the Copilot client headers issue (PR #13644 - missing `Editor-Version` header), the built-in `openclaw setup` command should work:
```bash
docker compose run --rm openclaw-cli setup
```
This will handle device flow within the container using `BROWSER=echo` to print the URL.

### Token Notes

- `ghu_` tokens from the Copilot device flow are **long-lived** (they don't expire on their own)
- OpenClaw exchanges the `ghu_` token for short-lived JWTs internally
- The Copilot client ID is `Iv1.b507a08c87ecfe98`

### Gateway Token

The gateway requires a token for API/UI access:
- Set in `.env` as `OPENCLAW_GATEWAY_TOKEN`
- Access Control UI: `https://openclaw.benlawson.dev/?token=<token>`

## Environment Variables

### Required (.env)
```bash
OPENCLAW_GATEWAY_TOKEN=<gateway-auth-token>
DISCORD_BOT_TOKEN=<discord-bot-token>
```

### Optional
```bash
OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:main
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_GATEWAY_BIND=lan
OLLAMA_API_KEY=ollama-local
MOLTBOOK_API_KEY=<moltbook-api-key>
DISCORD_WEBHOOK_URL=<webhook-for-notifications>
```

## Skills

### Moltbook Integration

TrollClaw has the Moltbook skill enabled for posting to the Moltbook social network:
```json
{
  "skills": {
    "entries": {
      "moltbook": {
        "enabled": true,
        "env": {
          "MOLTBOOK_API_KEY": "..."
        }
      }
    }
  }
}
```

## CLI Commands

### Shell Alias (Recommended)
```bash
alias openclaw='docker compose -f /mnt/e/Docker/openclaw/docker-compose.yml run --rm openclaw-cli'
```

### Common Commands
```bash
# Re-run setup (auth, model selection)
openclaw setup

# Check configuration
openclaw config get

# Change primary model
openclaw config set agents.defaults.model.primary "github-copilot/claude-sonnet-4.5"

# Run diagnostics
openclaw doctor

# Approve a DM pairing request
openclaw pairing approve discord <code>

# Send a test message
openclaw agent --message "Hello" --local
```

## Chat Commands (In Discord)

Send these in the allowed channel or DM:
| Command | Description |
|---------|-------------|
| `/status` | Session status (model, tokens, cost) |
| `/new` or `/reset` | Reset the session |
| `/compact` | Compact session context |
| `/think <level>` | Set thinking: off|minimal|low|medium|high|xhigh |
| `/verbose on|off` | Toggle verbose mode |
| `/usage off|tokens|full` | Usage footer style |

## Security

### Git-Crypt Encrypted Files
These files contain secrets and are encrypted in the repository:
- `openclaw/.env`
- `openclaw/config/openclaw.json`
- `openclaw/config/agents/**/auth-profiles.json`

### Discord Lockdown
- **Group Policy**: `allowlist` — only specified guilds/channels can interact
- **DM Policy**: `pairing` — new DM senders must be approved with a code
- **Require Mention**: Bot only responds when @mentioned in channels

## Troubleshooting

### Check Logs
```bash
docker logs openclaw-gateway
docker logs -f openclaw-gateway --tail 100
```

### Gateway Health
```bash
curl http://localhost:18789/health
```

### Run Diagnostics
```bash
docker compose run --rm openclaw-cli doctor
```

### Re-authenticate Copilot
If Copilot auth fails, re-run the device flow workaround (see Authentication section above).

### Common Issues

| Issue | Solution |
|-------|----------|
| "token invalid" | Re-run device flow workaround for fresh `ghu_` token |
| Bot not responding | Check Discord token, verify channel is in allowlist |
| Model unavailable | Verify auth-profiles.json has valid `ghu_` token |
| "Channel unresolved" | Guild/channel IDs may be wrong in config |
| Docker API unreachable | Verify socket-proxy is running and on same network |

### Restart Gateway
```bash
cd /mnt/e/Docker/openclaw
docker compose restart openclaw-gateway
```

## Integration

### SWAG Reverse Proxy
WebSocket proxy config at `swag/config/nginx/proxy-confs/openclaw.subdomain.conf`:
```nginx
location / {
    proxy_pass http://openclaw-gateway:18789;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### Homepage
Labels in docker-compose.yml provide Homepage integration:
- Group: `AI & Automation`
- URL: `https://openclaw.benlawson.dev/?token=...`

### Uptime Kuma
Automatic monitoring via SWAG labels:
- Monitor URL: `https://openclaw.benlawson.dev/`

### Docker Socket Proxy
The gateway uses `socket-proxy` for Docker API access:
- Network: `socket-proxy-net`
- Env: `DOCKER_HOST=tcp://socket-proxy:2375`
- Capabilities: Container listing, start/stop/restart, images, info, events, networks

## Useful Resources
- [OpenClaw Docs](https://docs.openclaw.ai/)
- [GitHub Copilot Models](https://docs.github.com/en/copilot)
- [Discord Developer Portal](https://discord.com/developers/applications)
