---
applyTo: 'open-webui/**'
---

# Open WebUI - AI Chat Interface

## Service Overview
Open WebUI is a feature-rich, self-hosted AI chat interface designed for Ollama and OpenAI-compatible APIs. It provides a ChatGPT-like experience with RAG support, document uploads, and model management.

## Container Configuration
- **Image**: `ghcr.io/open-webui/open-webui:main`
- **Container Name**: `open-webui`
- **Port**: `8080`

## Volume Mounts
```
./data:/app/backend/data    # User data, conversations, documents, settings
```

## Environment Variables
- `OLLAMA_BASE_URL=http://ollama:11434` - **CRITICAL**: URL to Ollama server
- `WEBUI_SECRET_KEY` - Session encryption key (change from default!)
- `WEBUI_NAME` - Custom branding name
- `PUID=1000` - User ID for file permissions
- `PGID=1000` - Group ID for file permissions
- `TZ=America/New_York` - Timezone

## Access
- **Local**: http://localhost:3333
- **External**: https://chat.benlawson.dev (via SWAG reverse proxy)

## First Time Setup
1. Navigate to http://localhost:3333
2. Create admin account (first user becomes admin)
3. Select model from dropdown (populated from Ollama)
4. Start chatting!

## Key Features

### Chat Interface
- Real-time streaming responses
- Markdown and LaTeX support
- Code syntax highlighting
- Conversation branching
- Export conversations (JSON, Markdown)
- Multi-model conversations

### Document Analysis (RAG)
- Upload PDFs, DOCX, TXT files
- Chat with your documents
- Reference documents with `#document-name`
- Document library management
- Automatic chunking and embedding

### Model Management
- Pull models directly from UI
- Delete unused models
- Create custom models with Modelfiles
- Switch models mid-conversation
- View model details and parameters

### Advanced Features
- **Web Search**: Integrate SearXNG, Google, Brave Search
- **Image Generation**: AUTOMATIC1111, ComfyUI, DALL-E support
- **Voice Input**: Speech-to-text
- **Multi-Model**: Query multiple models simultaneously
- **Functions**: Custom Python functions for extended capabilities
- **Pipelines**: Plugin framework for custom logic

## Integration with Ollama

Open WebUI connects to Ollama via the `proxynet` internal network:
```
http://ollama:11434
```

All models available in Ollama automatically appear in the Open WebUI model dropdown.

### Verify Connection
From within Open WebUI container:
```bash
docker exec open-webui curl http://ollama:11434/api/tags
```

## Homepage Integration
Open WebUI uses a custom icon for the Homepage dashboard.
- **Icon**: `homepage/config/icons/openwebui.png`
- **Label**: `homepage.icon=/icons/openwebui.png`

## User Management

### Admin Panel
Access via: Profile → Admin Panel

**Admin Capabilities**:
- Manage users and permissions
- Configure model access
- Set system prompts
- Enable/disable features
- View usage statistics

### Role-Based Access Control
- **Admin**: Full system access
- **User**: Standard chat access
- **Pending**: Awaiting admin approval

## Configuration

### Change Ollama URL
If Ollama is on different host, update in:
- Settings → Connections → Ollama API URL
- Or change `OLLAMA_BASE_URL` environment variable

### Enable Web Search
1. Settings → Web Search
2. Select provider (SearXNG recommended for privacy)
3. Add API key if required
4. Use in chat by prefixing: `search: your query`

### Custom Branding
Admin Panel → Settings:
- Upload custom logo
- Change color scheme
- Modify welcome message
- Set custom title

## API Access

Open WebUI provides OpenAI-compatible API:
```
http://localhost:3333/api
```

Use with any OpenAI-compatible client by changing the base URL.

## Common Operations

### Pull New Model
Settings → Models → Pull Model → Enter model name (e.g., `mistral`)

### View Conversations
All conversations are stored in `./data`

### Export Conversation
Click conversation menu → Export → Choose format (JSON/Markdown)

### Create Custom Model
Settings → Models → Create Model → Write Modelfile:
```
FROM llama3.2
PARAMETER temperature 0.8
SYSTEM You are a helpful assistant.
```

### View Logs
```bash
docker logs open-webui
```

### Restart Service
```bash
cd /mnt/e/Docker/open-webui
docker compose restart
```

## Troubleshooting

### Cannot Connect to Ollama
**Check Connection**:
```bash
docker exec open-webui curl http://ollama:11434/api/tags
```

**Common Issues**:
- Ollama container not running: `docker ps | grep ollama`
- Network mismatch: Both must be on `proxynet`
- Wrong URL in settings

**Fix**:
1. Verify both containers are running
2. Check they're on same network: `docker inspect ollama | grep proxynet`
3. Update URL in Settings → Connections

### Models Not Appearing
1. Ensure models are pulled in Ollama: `docker exec ollama ollama list`
2. Refresh Open WebUI page
3. Check connection to Ollama
4. Verify `OLLAMA_BASE_URL` is correct

### Login Issues
- Clear browser cache and cookies
- Check logs: `docker logs open-webui`
- Reset `WEBUI_SECRET_KEY` in `.env` and restart

### Slow Responses
- Check Ollama GPU usage: `docker exec ollama nvidia-smi`
- Try smaller model (e.g., `llama3.2:1b`)
- Reduce context length in Settings

### Document Upload Fails
- Check available disk space in `./data`
- Verify file format is supported (PDF, DOCX, TXT, MD)
- Check logs for specific error

## Security

### Secret Key
**IMPORTANT**: Change `WEBUI_SECRET_KEY` from default value!
```bash
# Generate secure key
openssl rand -base64 32
```
Update in `.env` and restart service.

### Authentication
- First user becomes admin
- Additional users require admin approval (configurable)
- Enable email verification in settings
- Configure OAuth providers (Google, GitHub, etc.)

### External Access
When exposing via SWAG reverse proxy:
- Enable HTTPS/SSL
- Consider additional authentication layer
- Set CORS settings appropriately
- Rate limit API endpoints

## Data Management

### Backup
All data is in `./data`:
- User accounts and settings
- Conversation history
- Uploaded documents
- Custom models

Backup this directory regularly.

### Reset/Clean Install
```bash
cd /mnt/e/Docker/open-webui
docker compose down
rm -rf data/*
docker compose up -d
```

## Integration with n8n

Use HTTP Request node to call Open WebUI API:
```
POST http://open-webui:8080/api/chat
Body: {
  "model": "llama3.2",
  "messages": [{"role": "user", "content": "Hello"}]
}
```

## Performance Optimization

### Embedding Model
Default uses sentence-transformers. Change in Settings → Documents:
- Use faster model for large document libraries
- Adjust chunk size based on use case

### Database
Uses SQLite by default. For production with many users, consider PostgreSQL.

### Caching
Enable response caching in Settings → Advanced for repeated queries.

## Common Modifications

### Change Port
Edit `docker-compose.yml`:
```yaml
ports:
  - 8080:8080  # Change first number for different host port
```

### Add PostgreSQL Database
```yaml
environment:
  - DATABASE_URL=postgresql://user:pass@postgres:5432/openwebui
```

### Enable Debug Mode
```yaml
environment:
  - WEBUI_DEBUG=true
```

## Resources
- Official Site: https://openwebui.com/
- Documentation: https://docs.openwebui.com/
- GitHub: https://github.com/open-webui/open-webui
- Discord: https://discord.gg/5rJgQTnV4s
- Model Library: https://openwebui.com/ (community models)
