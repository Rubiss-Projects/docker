# Glances Deployment Instructions for Pi

## Quick Deployment Steps

After pulling the latest changes from git, deploy Glances:

```bash
cd ~/docker/pi/glances
docker compose up -d
```

## Verify Deployment

Check that Glances is running:
```bash
docker ps | grep glances-pi
```

Expected output:
```
glances-pi    nicolargo/glances:latest-full   Up X minutes   0.0.0.0:61208->61208/tcp
```

## Access Glances

- **Web Interface**: http://192.168.50.216:61208
- **Homepage Widget**: Will automatically show Pi system stats

## Test the API

Verify the API is responding:
```bash
curl http://localhost:61208/api/4/cpu
```

## Troubleshooting

### Check Logs
```bash
docker logs glances-pi
```

### Restart Service
```bash
cd ~/docker/pi/glances
docker compose restart
```

### Check Network
```bash
docker network ls | grep proxynet
```

## What Glances Monitors

- CPU usage and load average
- Memory (RAM) usage
- Disk usage for all mounted filesystems
- CPU temperature (if available via sensors)
- Network I/O statistics
- System uptime
- Top processes by CPU/memory
- Docker container stats (via /var/run/docker.sock)

## Homepage Integration

Once deployed, the Homepage dashboard will automatically display:
- Real-time CPU usage
- Memory usage
- Disk usage
- CPU temperature
- System uptime

The widget refreshes automatically every few seconds.
