"""Run via docker exec -i swag python3 -, after deploying Transmission labels.

Edit the existing monitor in place, preserving its ID/history/notifications.
The SWAG mod otherwise deletes and recreates monitors when labels change.
"""
import os
import sys
import time

from uptime_kuma_api import UptimeKumaApi

sys.path.insert(0, "/app")
from auto_uptime_kuma.config_service import ConfigService
from auto_uptime_kuma.docker_service import DockerService
from auto_uptime_kuma.uptime_kuma_service import UptimeKumaService

config = ConfigService(os.environ["URL"])
service = UptimeKumaService(config)
service.api = UptimeKumaApi(os.environ["UPTIME_KUMA_URL"], timeout=30)
try:
    # Match the existing kuma-maintenance helper: the socket can connect before
    # Kuma has installed its login handler. Immediate library login is dropped.
    time.sleep(0.25)
    service.api.login(os.environ["UPTIME_KUMA_USERNAME"], os.environ["UPTIME_KUMA_PASSWORD"])
    service.load_data()
    old = service.get_monitor("transmission")
    if not old or old["id"] != 126:
        raise RuntimeError("Expected existing Transmission monitor 126; refusing to modify a replacement")
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
