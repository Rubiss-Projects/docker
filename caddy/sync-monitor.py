#!/usr/bin/env python3
"""Idempotently add Caddy's TLS/Plex monitor using the existing SWAG Kuma login."""

import importlib.util
from pathlib import Path
import subprocess

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/kuma-maintenance.py'
spec = importlib.util.spec_from_file_location('kuma_maintenance', SOURCE)
kuma = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kuma)

# Reuse the installed Socket.IO transport and credential environment. Wait for
# initial-info before login, as required by the current Kuma server/client pair.
INNER = r'''
import json
import os
import threading
import socketio

sio = socketio.Client(logger=False, engineio_logger=False, request_timeout=10)
info = threading.Event()
ready = threading.Event()
notifications_ready = threading.Event()
monitors = {}
notification_channels = []
sio.on('info', lambda *_args: info.set())
def receive(value):
    monitors.clear()
    monitors.update(value)
    ready.set()
sio.on('monitorList', receive)
def receive_notifications(value):
    notification_channels.clear()
    notification_channels.extend(value)
    notifications_ready.set()
sio.on('notificationList', receive_notifications)
def call(event, data=None):
    result = sio.call(event, data, timeout=15)
    if isinstance(result, dict) and result.get('ok') is False:
        raise RuntimeError(event + ' refused')
    return result
try:
    sio.connect(os.environ['UPTIME_KUMA_URL'].rstrip('/') + '/socket.io/', wait_timeout=15)
    if not info.wait(10):
        raise RuntimeError('Kuma initial info missing')
    call('login', {'username': os.environ.get('UPTIME_KUMA_USERNAME') or os.environ['UPTIME_KUMA_USER'],
                   'password': os.environ.get('UPTIME_KUMA_PASSWORD') or os.environ['UPTIME_KUMA_PASS'], 'token': ''})
    call('getMonitorList')
    if not ready.wait(10) or not notifications_ready.wait(10):
        raise RuntimeError('Kuma monitors/notification channels missing')
    rows = list(monitors.values())
    parents = [m for m in rows if m.get('name') == 'Infrastructure' and m.get('type') == 'group']
    plex = [m for m in rows if m.get('url') == 'http://plex:32400/identity']
    existing = [m for m in rows if m.get('name') == 'caddy']
    if len(parents) != 1 or len(plex) != 1 or len(existing) > 1:
        raise RuntimeError('Monitor/parent/notification source not unique')
    # The Plex monitor also invokes Docker self-heal through an n8n webhook.
    # This native service uses its own watchdog; inherit only its Discord alerts.
    assigned = plex[0].get('notificationIDList', {})
    notifications = {}
    for channel in notification_channels:
        config = json.loads(channel['config']) if isinstance(channel.get('config'), str) else channel.get('config', {})
        key = str(channel['id'])
        if assigned.get(key) and config.get('type') == 'discord':
            notifications[key] = True
    if not notifications:
        raise RuntimeError('Plex Discord notification routing absent')
    desired = {'name': 'caddy', 'type': 'http', 'url': 'https://plex-remote.benlawson.dev:18443/identity',
               'method': 'GET', 'interval': 60, 'retryInterval': 30, 'maxretries': 2, 'timeout': 10,
               'maxredirects': 0, 'accepted_statuscodes': ['200'], 'ignoreTls': False,
               'expiryNotification': True, 'parent': parents[0]['id'], 'active': True, 'conditions': [],
               'notificationIDList': notifications, 'description': 'Native Ubuntu Caddy -> Plex; TLS expiry alerts enabled. Caddy-only watchdog recovery.'}
    if existing:
        if existing[0].get('url') != desired['url']:
            raise RuntimeError('Existing caddy monitor has a different owner URL')
        desired = {**existing[0], **desired}
        result = call('editMonitor', desired)
        monitor_id = existing[0]['id']
    else:
        result = call('add', desired)
        monitor_id = result['monitorID']
    print(json.dumps({'monitor_id': monitor_id, 'name': 'caddy', 'notification_count': len(notifications)}))
finally:
    sio.disconnect()
'''


if __name__ == '__main__':
    env = kuma.build_exec_env([])
    options = [item for key in kuma.KUMA_ENV_KEYS if env.get(key) for item in ('-e', key)]
    result = subprocess.run(['docker', 'exec', '-i', *options, 'swag', 'python3', '-'],
                            input=INNER, text=True, env=env, timeout=90)
    raise SystemExit(result.returncode)
