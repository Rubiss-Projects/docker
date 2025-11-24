---
applyTo: 'lazytainer/**'
---

# Lazytainer - Serverless/Lazy Loading Infrastructure

## Overview
Lazytainer is a proxy that automatically starts and stops Docker containers based on network traffic. It is used to "lazy load" services that are not frequently used, saving system resources (RAM/CPU) when services are idle.

## Architecture
- **Lazytainer**: Acts as the gateway. It listens on specific ports (e.g., 8080, 11434) and routes traffic to the target container. If the container is stopped, it holds the request, starts the container, and then forwards the request.
- **Sidecar (`lazytainer-init`)**: A helper container that:
    - Runs `socat` proxies to handle connection retries during wake-up.
    - Exposes a "smart" healthcheck endpoint.
- **Network Strategy**: Target services run on the shared `proxynet` network. They are **not** in the `lazytainer` network namespace. This avoids port conflicts and allows services to communicate with each other (e.g., WebUI -> Ollama) directly.

## Configuration Pattern

### 1. Define Group in Lazytainer
In `lazytainer/docker-compose.yml`, define the group configuration in labels. Map the external port to the internal port of the target service.

```yaml
services:
  lazytainer:
    # ...
    ports:
      - "3333:8080"   # WebUI (Host:Container)
      - "11434:11434" # Ollama
    labels:
      # Configuration for 'ai' group (Open WebUI)
      - "lazytainer.group.ai.ports=8080"
      - "lazytainer.group.ai.inactiveTimeout=300" # 5 minutes
      - "lazytainer.group.ai.pollRate=30"         # Check every 30s
      - "lazytainer.group.ai.minPacketThreshold=1"
      - "lazytainer.group.ai.sleepMethod=stop"
      
      # Configuration for 'ollama' group
      - "lazytainer.group.ollama.ports=11434"
      - "lazytainer.group.ollama.inactiveTimeout=300"
      # ...
```

### 2. Configure Target Service
In the target service's `docker-compose.yml`:
- **Network**: Must be on `proxynet`.
- **Labels**: Assign the service to the Lazytainer group.
- **Ports**: Do NOT expose ports to the host (Lazytainer handles external access).

```yaml
services:
  myservice:
    container_name: myservice
    networks:
      - proxynet
    labels:
      - "lazytainer.group=ai"  # Matches group defined in Lazytainer
```

### 3. Smart Healthcheck (Bypass)
To monitor the service without waking it up:
1.  **Sidecar**: The `lazytainer-init` service exposes port `8081` (mapped to host `3334`).
2.  **Script**: `healthcheck.sh` checks the container status via Docker socket.
    - **HTTP 200**: Running OR Sleeping (Clean Exit 0/137/143)
    - **HTTP 500**: Crashed (Non-zero exit code)
3.  **Uptime Kuma**: Point monitor to `http://lazytainer:8081/health/{container_name}`.
    - Example: `http://lazytainer:8081/health/ollama`
    - Example: `http://lazytainer:8081/health/open-webui`
    - Note: Use `lazytainer` hostname, not `lazytainer-init`, as they share the network stack.

### 4. Connection Handling (connect.sh)
The `lazytainer-init` container uses a custom `connect.sh` script to handle DNS resolution during wake-up.
- When a container is stopped, Docker DNS may return NXDOMAIN.
- The script waits for the container name to resolve before attempting to connect.
- This prevents "Connection Refused" errors during the boot phase.

### 5. Public Healthcheck Endpoint (Optional)
To expose the healthcheck via your domain (e.g., `https://chat.benlawson.dev/health/open-webui`), configure Nginx Proxy Manager:

1.  **Edit Host**: Go to the Proxy Host configuration (e.g., `chat.benlawson.dev`).
2.  **Custom Locations**: Add a new location.
    - **Location**: `/health/open-webui`
    - **Scheme**: `http`
    - **Forward Host**: `lazytainer` (or the IP of the host)
    - **Forward Port**: `8081` (The healthcheck listener port)
3.  **Uptime Kuma**: Update the monitor URL to the public domain:
    - `https://chat.benlawson.dev/health/open-webui`

This allows Uptime Kuma to verify the entire stack (DNS -> NPM -> Lazytainer -> Service Status).

## Troubleshooting
- **Service won't start**: Check `docker logs lazytainer`.
- **Immediate restart**: Ensure `pollRate` is not too aggressive or external monitoring isn't hitting the main port.
- **Healthcheck fails**: Verify `lazytainer-init` is running and has access to `/var/run/docker.sock`.
- **DNS Errors**: Ensure services are on the same `proxynet` network.
