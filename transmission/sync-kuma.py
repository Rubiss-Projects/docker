"""Run via docker exec -i swag python3 -, after deploying Transmission labels.

Edit the existing monitor in place, preserving its ID/history/notifications.
The SWAG mod otherwise deletes and recreates monitors when labels change.
"""
import os
import sys

sys.path.insert(0, "/app")
from auto_uptime_kuma.config_service import ConfigService
from auto_uptime_kuma.docker_service import DockerService
from auto_uptime_kuma.uptime_kuma_service import UptimeKumaService

config = ConfigService(os.environ["URL"])
service = UptimeKumaService(config)
if not service.connect(os.environ["UPTIME_KUMA_URL"], os.environ["UPTIME_KUMA_USERNAME"], os.environ["UPTIME_KUMA_PASSWORD"]):
    raise RuntimeError("Kuma unavailable")
try:
    service.load_data()
    old = service.get_monitor("transmission")
    if not old:
        raise RuntimeError("Existing Transmission monitor not found; refusing to recreate history")
    docker = DockerService("swag.uptime-kuma")
    labels = docker.client.containers.get("transmission").labels
    desired = service.build_monitor_data("transmission", docker.parse_container_labels(labels, ".monitor."))
    if desired.get("type") != "docker":
        raise RuntimeError("Deploy functional-health labels before syncing Kuma")
    service.api.edit_monitor(old["id"], type=desired["type"], docker_container="transmission",
                             docker_host=desired["docker_host"], description=desired["description"])
    config.create_config("transmission", desired)
    print(f'Transmission monitor {old["id"]} now uses functional Docker health; history preserved.')
finally:
    service.disconnect()
