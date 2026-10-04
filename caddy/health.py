#!/usr/bin/env python3
"""Watchdog leaf: repair Caddy alone, with maintenance and restart-loop guards."""

import argparse
import fcntl
import http.client
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time

UNIT = 'caddy-plex.service'
HOLD = Path('/run/caddy-plex.maintenance')
ATTEMPT = Path('/var/lib/caddy-plex-control/last-watchdog-attempt')


class LocalHTTPS(http.client.HTTPSConnection):
    def connect(self):
        # Keep public SNI/certificate validation without depending on WAN hairpin.
        self.sock = self._context.wrap_socket(
            socket.create_connection(('192.168.50.40', 18443), self.timeout),
            server_hostname=self.host)


def healthy():
    connection = LocalHTTPS('plex-remote.benlawson.dev', timeout=2,
                            context=ssl.create_default_context())
    try:
        connection.request('GET', '/healthz', headers={'Host': 'plex-remote.benlawson.dev:18443'})
        response = connection.getresponse()
        return response.status == 200 and response.read(32) == b'ok'
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def state():
    result = subprocess.run(['systemctl', 'show', UNIT, '--property=ActiveState', '--value'],
                            capture_output=True, text=True, check=True, timeout=3)
    return result.stdout.strip()


def check(repair=False):
    # Disabling the service or creating the hold is an intentional operator stop.
    enabled = subprocess.run(['systemctl', 'is-enabled', '--quiet', UNIT], capture_output=True).returncode == 0
    if not enabled or HOLD.exists():
        print('Caddy intentionally disabled/held; no remediation')
        return 0
    if healthy():
        print('Caddy TLS health passed')
        return 0
    if not repair:
        return 1
    for _ in range(2):
        time.sleep(2)
        if healthy():
            return 0
    if HOLD.exists() or state() not in ('active', 'inactive', 'failed'):
        return 1
    if ATTEMPT.exists() and time.time() - float(ATTEMPT.read_text()) < 600:
        print('Caddy repair cooldown; alert remains active')
        return 1
    # Validate source/certificate before touching the existing process.
    result = subprocess.run(['/usr/local/bin/caddy-plex', 'validate', '--config',
                             '/etc/caddy-plex/Caddyfile', '--adapter', 'caddyfile'],
                            capture_output=True, timeout=5)
    if result.returncode != 0:
        print('Caddy configuration validation failed; no restart')
        return 1
    if HOLD.exists() or subprocess.run(['systemctl', 'is-enabled', '--quiet', UNIT], capture_output=True).returncode != 0:
        return 1
    ATTEMPT.write_text(str(time.time()))
    subprocess.run(['systemctl', 'reset-failed', UNIT], check=True, timeout=3)
    subprocess.run(['systemctl', 'restart', '--no-block', UNIT], check=True, timeout=3)
    # Do not signal a pending transition or promote a late result to a pass.
    for _ in range(4):
        time.sleep(1)
        if healthy():
            print('Caddy-only repair passed')
            return 0
    print('Caddy repair pending/failed; Docker and Plex left running')
    return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    with open('/run/lock/caddy-plex.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Caddy configuration/certificate operation owns recovery; deferred')
            raise SystemExit(0)
        raise SystemExit(check(args.repair))
