# Raspberry Pi maintenance

## Docker image cleanup

`docker-image-cleanup.timer` runs daily at 04:30 with up to 30 minutes of
random delay. It removes images that have not been used by a container for at
least seven days. Docker preserves images referenced by running or stopped
containers. The cleanup does not prune containers, volumes, networks, or
application data.

Install or refresh the user timer:

```bash
./pi/scripts/install-docker-image-cleanup.sh
```

Inspect the schedule and logs:

```bash
systemctl --user list-timers docker-image-cleanup.timer
journalctl --user -u docker-image-cleanup.service
```

Override the seven-day retention window for a manual run:

```bash
DOCKER_IMAGE_MAX_AGE=336h ./pi/scripts/docker-image-cleanup.sh
```
