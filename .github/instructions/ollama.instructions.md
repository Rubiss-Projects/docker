---
applyTo: 'ollama/**'
---

# Ollama LLM Server

## Service Overview
Ollama is a local LLM server that allows you to run large language models on your own hardware with GPU acceleration.

## Container Configuration
- **Image**: `ollama/ollama`
- **Container Name**: `ollama`
- **Port**: `11434` (Internal only, exposed via Lazytainer)
- **Network**: `proxynet`
- **GPU**: NVIDIA GPU with CUDA support

## Lazy Loading (Lazytainer)
This service is configured to sleep when idle to save GPU and system resources.
- **Manager**: `lazytainer` service monitors traffic on port `11434`.
- **Wake-up**: Accessing the API automatically starts the container.
- **Timeout**: Stops after 5 minutes of inactivity.
- **Healthcheck**: Monitor via `http://lazytainer:8081/health/ollama` (Returns 200 even if sleeping).

### Configuration Labels
```yaml
labels:
  - "lazytainer.group=ollama" # Assign to lazytainer group
```

## Volume Mounts
```
./data:/root/.ollama            # Model storage and configuration
/usr/lib/wsl/drivers:/usr/lib/wsl/drivers:ro  # WSL NVIDIA drivers (read-only)
/usr/lib/wsl/lib:/usr/lib/wsl/lib:ro          # WSL NVIDIA libraries (read-only)
```

## GPU Configuration
**CRITICAL**: This service requires NVIDIA GPU with proper Docker GPU support.

### Deploy Configuration
```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu, compute, utility]
```

### Environment Variables
- `NVIDIA_VISIBLE_DEVICES=all` - Make all GPUs visible to container
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility` - Required CUDA capabilities
- `PUID=1000` - User ID for file permissions
- `PGID=1000` - Group ID for file permissions
- `TZ=America/New_York` - Timezone

### WSL2 GPU Requirements
- Docker Desktop with WSL2 backend
- NVIDIA GPU drivers installed on Windows
- WSL NVIDIA driver paths mounted into container
- NVIDIA Container Toolkit (handled by Docker Desktop)

## Model Management

### Pull Models
```bash
docker exec ollama ollama pull llama3.2
docker exec ollama ollama pull gemma3
docker exec ollama ollama pull mistral
```

### List Models
```bash
docker exec ollama ollama list
```

### Run Model Interactively
```bash
docker exec -it ollama ollama run llama3.2
```

### Remove Model
```bash
docker exec ollama ollama rm model_name
```

## API Usage

### Generate Response
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2",
  "prompt": "Why is the sky blue?"
}'
```

### Chat Endpoint
```bash
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [
    { "role": "user", "content": "Hello!" }
  ]
}'
```

### List Available Models API
```bash
curl http://localhost:11434/api/tags
```

## Model Resources

### Memory Requirements
- **1B-3B models**: 4-8GB VRAM or 8GB RAM
- **7B models**: 8GB VRAM or 16GB RAM
- **13B models**: 16GB VRAM or 32GB RAM
- **33B+ models**: 24GB+ VRAM or 64GB+ RAM

### Popular Models
- `llama3.2` - Meta's Llama 3.2 (3B, fast and capable)
- `gemma3` - Google's Gemma 3 (4B, good performance)
- `mistral` - Mistral AI (7B, excellent reasoning)
- `codellama` - Code-focused Llama (7B, for programming)
- `deepseek-r1` - DeepSeek reasoning model (7B)
- `phi4` - Microsoft Phi-4 (14B, high quality)

Full model library: https://ollama.com/library

## Integration with Other Services

### Open WebUI
Open WebUI connects automatically via `http://ollama:11434`

### n8n Workflows
Use HTTP Request nodes to call Ollama:
- URL: `http://ollama:11434/api/generate`
- Method: POST
- Body: `{"model": "llama3.2", "prompt": "Your prompt"}`

### Custom Applications
Any service on `proxynet` can access Ollama at `http://ollama:11434`

## Troubleshooting

### GPU Out of Memory
**Symptoms**: `cudaMalloc failed: out of memory`

**Solutions**:
1. **Restart WSL**: `wsl --shutdown` then restart Docker Desktop
   - This clears GPU memory fragmentation
2. **Use smaller models**: Try `llama3.2:1b` instead of larger variants
3. **Close GPU applications**: Browser hardware acceleration, games, etc.

### GPU Not Detected
```bash
docker exec ollama nvidia-smi
```
Should show your GPU. If not:
- Restart Docker Desktop
- Verify WSL2 backend is enabled
- Check Windows has latest NVIDIA drivers

### Model Won't Load
Check logs for specific errors:
```bash
docker logs ollama --tail 50
```

Common issues:
- Insufficient disk space in `./data`
- Corrupted model download (delete and re-pull)
- GPU memory already allocated (restart WSL)

### Connection Refused
Ensure service is running:
```bash
docker ps | grep ollama
```

Test connectivity from another container:
```bash
docker exec open-webui curl http://ollama:11434/api/tags
```

## Performance Optimization

### Context Window
Default is 4096 tokens. Reduce for faster responses:
```bash
docker exec ollama ollama run llama3.2 --ctx-size 2048
```

### GPU Layers
All layers offload to GPU by default. For mixed CPU/GPU:
```bash
# Force CPU only
docker exec ollama sh -c 'OLLAMA_NUM_GPU=0 ollama run llama3.2'
```

## Security Notes
- Ollama has NO authentication by default
- Use Nginx Proxy Manager with auth for external access
- API is exposed only to `proxynet` internal network
- Models stored locally, no data sent to external services

## Backup
Models are stored in `./data`. Back up this directory to preserve downloaded models and avoid re-downloading.

## Common Modifications

### Change Default Context Size
Add to environment variables:
```yaml
environment:
  - OLLAMA_CONTEXT_LENGTH=8192
```

### Limit GPU Memory
Add to environment variables:
```yaml
environment:
  - OLLAMA_GPU_OVERHEAD=512  # MB of reserved GPU memory
```

### Enable Debug Logging
```yaml
environment:
  - OLLAMA_DEBUG=1
```
