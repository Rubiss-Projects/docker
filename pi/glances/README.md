# Glances - System Monitoring for Raspberry Pi

Glances is a cross-platform system monitoring tool that displays CPU, memory, disk, network, and process information in real-time.

## Configuration

### Environment Variables
- `TZ`: Timezone (America/Chicago)
- `GLANCES_OPT`: Glances startup options (-w for web server mode)

### Ports
- `61208`: Glances web interface

### Volumes
- `/var/run/docker.sock`: Docker container monitoring (read-only)
- `/etc/os-release`: OS information (read-only)

### Special Settings
- `pid: host`: Enables host-level process monitoring
- Uses `latest-full` image for complete feature set

## Features

The Glances widget in Homepage will display:
- CPU usage and load average
- Memory usage (RAM)
- Disk usage
- CPU temperature (if available)
- System uptime
- Network I/O

## Access

- **Web Interface**: http://192.168.50.216:61208
- **Homepage Widget**: Integrated in "Raspberry Pi" section

## Homepage Integration

The service is automatically discovered by Homepage via Docker labels:
- Group: Raspberry Pi
- Name: Pi System Monitor
- Widget Type: glances (version 4)
- Displays real-time system metrics

## Management

### Start Service
```bash
docker compose up -d
```

### Stop Service
```bash
docker compose down
```

### View Logs
```bash
docker logs glances-pi
```

### Restart Service
```bash
docker compose restart
```

## Notes

- Glances runs in web server mode (-w flag) for API access
- Homepage widget automatically polls the Glances API every few seconds
- The `latest-full` image includes all sensors and monitoring features
- `pid: host` allows Glances to see all system processes, not just container processes
