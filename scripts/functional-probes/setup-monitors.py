"""Reconcile functional monitors inside the existing SWAG integration environment.

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
]
# The two former push monitors retain their IDs, history and dashboard links.
HTTP_CHECKS = {
    "Internet reachability": (
        "https://connectivitycheck.gstatic.com/generate_204",
        "204",
        None,
    ),
    "Cloudflare internet reachability": (
        "https://www.cloudflare.com/cdn-cgi/trace",
        "200",
        "fl=",
    ),
    "External tunnel route": (
        "https://audiobookshelf.benlawson.dev/healthcheck",
        "200",
        "OK",
    ),
}
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
    for name, (url, status, keyword) in HTTP_CHECKS.items():
        label = LABEL + name
        matches = [m for m in inventory.values() if m["name"] == label]
        if len(matches) > 1:
            raise RuntimeError("Ambiguous monitor: " + name)
        fields = {
            "name": label,
            "type": "keyword" if keyword else "http",
            "method": "GET",
            "url": url,
            "keyword": keyword,
            "accepted_statuscodes": [status],
            "interval": 60,
            "retryInterval": 60,
            "timeout": 10,
            "maxredirects": 0,
            "ignoreTls": False,
            "upsideDown": False,
            "invertKeyword": False,
            "headers": json.dumps({"Cache-Control": "no-cache"}),
            "pushToken": None,
        }
        if matches:
            monitor = call("getMonitor", matches[0]["id"])["monitor"]
            if monitor["type"] not in ("push", fields["type"]):
                raise RuntimeError("Unexpected monitor type: " + name)
            if any(monitor.get(k) != v for k, v in fields.items()):
                call("editMonitor", {**monitor, **fields})
            monitor_id = monitor["id"]
        else:
            monitor_id = call(
                "add",
                {
                    **fields,
                    "active": True,
                    "conditions": [],
                    "notificationIDList": {},
                    "maxretries": 0,
                },
            )["monitorID"]
        print(f"{name}: Kuma monitor {monitor_id}", file=sys.stderr)
    json.dump(output, sys.stdout)
finally:
    client.disconnect()
