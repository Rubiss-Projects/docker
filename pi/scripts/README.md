# Raspberry Pi maintenance

## Docker image cleanup

`docker-image-cleanup.timer` runs daily at 04:30 with up to 30 minutes of
random delay. It records when each image is first observed without a container
reference and removes it after it remains unused for seven days. Images
referenced by running or stopped containers are never cleanup candidates. The
cleanup does not prune containers, volumes, networks, or application data.
The installer enables and verifies systemd user lingering so the timer remains
active when `rubiss` is not logged in.

Install or refresh the user timer:

```bash
./pi/scripts/install-docker-image-cleanup.sh
```

Inspect the schedule and logs:

```bash
systemctl --user list-timers docker-image-cleanup.timer
journalctl --user -u docker-image-cleanup.service
```

Override the seven-day retention window for a manual run (in hours):

```bash
DOCKER_UNUSED_IMAGE_RETENTION_HOURS=336 ./pi/scripts/docker-image-cleanup.sh
```
