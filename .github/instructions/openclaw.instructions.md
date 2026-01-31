---
applyTo: 'openclaw/**'
---

# OpenClaw AI Gateway

## Service Overview
OpenClaw is a personal AI assistant that runs on your own devices. It provides a WebSocket-based gateway (control plane) that connects to multiple messaging channels (WhatsApp, Telegram, Slack, Discord, Signal, iMessage, etc.) and provides AI assistant capabilities through various LLM providers.

**Key Concept**: The Gateway is the control plane — it manages sessions, channels, tools, and events. The product is the AI assistant that answers you across connected channels.

## Container Configuration
- **Gateway Image**: `ghcr.io/openclaw/openclaw:main` (or build locally with `openclaw:local`)
- **Gateway Container**: `openclaw-gateway`
- **CLI Container**: `openclaw-cli`
- **Gateway Port**: `18789` (WebSocket/HTTP)
- **Bridge Port**: `18790` (for mobile nodes)
- **Networks**: `proxynet`, `ollama-net`

## Volume Mounts
```
${OPENCLAW_CONFIG_DIR}:/home/node/.openclaw          # Configuration and credentials
${OPENCLAW_WORKSPACE_DIR}:/home/node/.openclaw/workspace  # Agent workspace (skills, agents)
```

## Environment Variables

### Required
| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCLAW_GATEWAY_TOKEN` | Authentication token for Gateway UI/API | Generate with `openssl rand -hex 32` |
| `OPENCLAW_CONFIG_DIR` | Host path to config directory | `./config` |
| `OPENCLAW_WORKSPACE_DIR` | Host path to workspace directory | `./config/workspace` |

### Optional
| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCLAW_IMAGE` | Docker image to use | `ghcr.io/openclaw/openclaw:main` |
| `OPENCLAW_GATEWAY_PORT` | Gateway WebSocket/HTTP port | `18789` |
| `OPENCLAW_BRIDGE_PORT` | Bridge port for mobile nodes | `18790` |
| `OPENCLAW_GATEWAY_BIND` | Network binding mode | `lan` |
| `OLLAMA_API_KEY` | API key for local Ollama (can be any string) | `ollama-local` |
| `HOME` | Home directory inside container | `/home/node` |
| `TERM` | Terminal type | `xterm-256color` |

### Channel Tokens (set in .env or config)
| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `SLACK_BOT_TOKEN` | Slack bot token |
| `SLACK_APP_TOKEN` | Slack app-level token |

## Network Configuration

### Required Networks
```yaml
networks:
  proxynet:    # For SWAG reverse proxy and inter-service communication
    external: true
    name: proxynet
  ollama-net:  # For local LLM access via Ollama
    external: true
    name: ollama-net
```

**Network Purpose**:
- `proxynet`: Enables SWAG reverse proxy access and communication with Homepage
- `ollama-net`: Connects to local Ollama LLM server for AI inference

## Architecture

### Gateway Mode
```
Messaging Channels (WhatsApp/Telegram/Slack/Discord/etc.)
               │
               ▼
┌───────────────────────────────┐
│            Gateway            │
│       (control plane)         │
│     ws://127.0.0.1:18789      │
└──────────────┬────────────────┘
               │
               ├─ Pi agent (RPC)
               ├─ CLI (openclaw …)
               ├─ WebChat UI
               ├─ Control UI
               └─ iOS / Android nodes
```

### Two-Container Pattern
This deployment uses two containers:
1. **openclaw-gateway**: Long-running daemon that handles all connections
2. **openclaw-cli**: Ephemeral container for running CLI commands (onboard, config, etc.)

## Configuration Files

### Primary Config (`config/openclaw.json`)
```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "copilot-proxy/claude-opus-4.5"
      },
      "workspace": "/home/node/.openclaw/workspace"
    }
  },
  "gateway": {
    "auth": {
      "mode": "token",
      "token": "${OPENCLAW_GATEWAY_TOKEN}"
    },
    "port": 18789,
    "bind": "lan"
  }
}
```

### Directory Structure
```
config/
├── openclaw.json        # Main configuration
├── agents/              # Agent definitions
├── canvas/              # Canvas data
├── cron/                # Cron job definitions
├── identity/            # Identity configuration
├── workspace/           # Agent workspace root
│   └── skills/          # Installed skills
└── exec-approvals.json  # Tool execution approvals
```

## Model Providers

### Using Ollama (Local LLMs)
To use local Ollama models, configure in `openclaw.json`:
```json
{
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://ollama:11434/v1",
        "apiKey": "ollama-local",
        "api": "openai-completions"
      }
    }
  }
}
```

### Using Copilot Proxy
For GitHub Copilot models via proxy:
```json
{
  "models": {
    "providers": {
      "copilot-proxy": {
        "baseUrl": "http://localhost:3000/v1",
        "apiKey": "n/a",
        "api": "openai-completions"
      }
    }
  }
}
```

### Cloud Providers (Anthropic/OpenAI)
For direct API access, configure with your API keys:
```json
{
  "models": {
    "providers": {
      "anthropic": { "apiKey": "${ANTHROPIC_API_KEY}" },
      "openai": { "apiKey": "${OPENAI_API_KEY}" }
    }
  }
}
```

## CLI Commands

### Shell Alias Setup (Recommended)
Add this alias to your `~/.bashrc` for easier CLI access:
```bash
echo "alias openclaw='docker compose -f /mnt/e/Docker/openclaw/docker-compose.yml run --rm openclaw-cli'" >> ~/.bashrc
source ~/.bashrc
```

After setup, you can run commands directly:
```bash
# Instead of: docker compose run --rm openclaw-cli agent --message "Hello"
openclaw agent --message "Hello"

# Help
openclaw --help

# Configuration
openclaw config get
openclaw config set agents.defaults.model.primary "ollama/llama3.2:3b"

# Agent interaction
openclaw agent --agent main --local --message "Hello"
```

### Full Docker Compose Commands
Run commands via the CLI container:
```bash
# Run onboarding wizard
docker compose run --rm openclaw-cli onboard

# Health check
docker compose exec openclaw-gateway node dist/index.js health --token "$OPENCLAW_GATEWAY_TOKEN"

# Channel management
docker compose run --rm openclaw-cli channels login          # WhatsApp QR
docker compose run --rm openclaw-cli channels add --channel telegram --token "TOKEN"
docker compose run --rm openclaw-cli channels add --channel discord --token "TOKEN"

# Send a message
docker compose run --rm openclaw-cli message send --to "+1234567890" --message "Hello"

# Agent interaction
docker compose run --rm openclaw-cli agent --message "Hello" --thinking high

# Diagnostics
docker compose run --rm openclaw-cli doctor
```

## Chat Commands (In-Channel)
Send these in connected channels:
- `/status` — Session status (model + tokens, cost)
- `/new` or `/reset` — Reset the session
- `/compact` — Compact session context
- `/think <level>` — off|minimal|low|medium|high|xhigh
- `/verbose on|off` — Toggle verbose mode
- `/usage off|tokens|full` — Usage footer
- `/restart` — Restart gateway (owner-only)

## Security Considerations

### Gateway Authentication
Always use token authentication in production:
```json
{
  "gateway": {
    "auth": {
      "mode": "token",
      "token": "your-secure-token"
    }
  }
}
```

### Channel Allowlists
Configure allowlists to control who can interact:
```json
{
  "channels": {
    "whatsapp": {
      "allowFrom": ["+1234567890"]
    },
    "telegram": {
      "allowFrom": ["username1", "username2"]
    },
    "discord": {
      "dm": {
        "policy": "pairing",
        "allowFrom": ["user_id1"]
      }
    }
  }
}
```

### DM Policy
Default `dmPolicy="pairing"` requires approval for new senders:
```bash
# Approve a pairing request
docker compose run --rm openclaw-cli pairing approve <channel> <code>
```

## Troubleshooting

### Check Container Logs
```bash
docker logs openclaw-gateway
docker logs -f openclaw-gateway --tail 100
```

### Gateway Health Check
```bash
curl http://localhost:18789/health
```

### Run Diagnostics
```bash
docker compose run --rm openclaw-cli doctor
```

### Common Issues
- **"token invalid"**: Ensure `OPENCLAW_GATEWAY_TOKEN` matches config
- **Model unavailable**: Check model provider configuration and network
- **Channel not connecting**: Verify tokens and channel configuration
- **Permission errors**: Check PUID/PGID match volume ownership

## Integration with Other Services

### Ollama
Ensure `ollama-net` network is created and Ollama container is running:
```bash
docker network create ollama-net
```

### SWAG Reverse Proxy
Use WebSocket proxy config for the gateway:
```nginx
location / {
    proxy_pass http://openclaw-gateway:18789;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

## Useful Resources
- [Official Docs](https://docs.openclaw.ai/)
- [GitHub Repository](https://github.com/openclaw/openclaw)
- [Configuration Reference](https://docs.openclaw.ai/gateway/configuration)
- [Docker Guide](https://docs.openclaw.ai/install/docker)
- [Channel Setup](https://docs.openclaw.ai/channels)
- [Skills (ClawHub)](https://clawhub.com/)
