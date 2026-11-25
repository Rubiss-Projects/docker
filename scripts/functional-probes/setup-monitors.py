"""Reconcile dedicated push monitors inside the existing SWAG integration environment.

Run through docker exec -i swag python3 -. Output contains push credentials and
must be redirected to a private file on BEN-SERVER.
"""

import json
import os
import secrets
import sys
import threading

import socketio

NAMES = [
    "Plex library read",
    "HDHomeRun tune",
    "DVR recording path",
    "Completed import",
    "Library read",
    "Database-backed vault read",
    "Last successful backup",
    "Accessory control",
    "Workflow execution",
    "Internet reachability",
    "External tunnel route",
]
LABEL = "Executive health · "
client = socketio.Client()
received = threading.Event()
inventory = {}


@client.on("monitorList")
def full_list(data):
    inventory.update(data)
    received.set()


def call(event, data=None):
    response = client.call(event, data, timeout=30)
    if not response.get("ok"):
        raise RuntimeError("Kuma rejected " + event)
    return response


client.connect(
    os.environ["UPTIME_KUMA_URL"].rstrip("/") + "/socket.io/", wait_timeout=30
)
try:
    call(
        "login",
        {
            "username": os.environ["UPTIME_KUMA_USERNAME"],
            "password": os.environ["UPTIME_KUMA_PASSWORD"],
            "token": "",
        },
    )
    call("getMonitorList")
    if not received.wait(15):
        raise RuntimeError("Missing monitor inventory")
    output = {}
    for name in NAMES:
        label = LABEL + name
        matches = [m for m in inventory.values() if m["name"] == label]
        if len(matches) > 1 or (matches and matches[0]["type"] != "push"):
            raise RuntimeError("Ambiguous monitor: " + name)
        if matches:
            monitor_id = matches[0]["id"]
        else:
            monitor_id = call(
                "add",
                {
                    "name": label,
                    "type": "push",
                    "interval": 450,
                    "retryInterval": 60,
                    "maxretries": 0,
                    "active": True,
                    "accepted_statuscodes": ["200-299"],
                    "notificationIDList": {},
                    "conditions": [],
                    "pushToken": secrets.token_hex(16),
                },
            )["monitorID"]
        monitor = call("getMonitor", monitor_id)["monitor"]
        if not monitor.get("pushToken"):
            raise RuntimeError("Kuma did not issue a push token")
        output[name] = {"id": monitor_id, "token": monitor["pushToken"]}
    json.dump(output, sys.stdout)
finally:
    client.disconnect()
