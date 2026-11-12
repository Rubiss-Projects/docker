"""UPS-only short Docker stop, clean NAS unmount, authenticated release, poweroff.

Run as a separate root oneshot: the regular guard's filesystem sandbox must not
be widened. Never use forced/lazy unmount or report release after an error.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import uuid

from native_ups_guard import ROOT


def run(args, timeout):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=timeout)


def main():
    if os.geteuid() != 0 or socket.gethostname() != 'ben-server':
        raise ValueError('Only the admitted server may release NAS storage')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    intent = json.loads((ROOT / 'shutdown-intent.json').read_text())
    if intent.get('boot') != boot or intent.get('decision') not in {
            'critical', 'sustained-battery', 'battery-status-lost'}:
        raise ValueError('A current UPS shutdown intent is required')
    ssh = ['ssh', '-F', '/etc/ups-cascade/ssh_config', 'pi']
    event = None
    try:
        event = str(uuid.UUID(run([*ssh, f'begin {boot}'], 8).stdout.strip()))
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Pi handshake unavailable; retain NAS fallback', flush=True)
    try:
        # Bound only this UPS shutdown. The ordinary maintenance allowance is
        # unchanged, and /run disappears at reboot.
        folder = Path('/run/systemd/system/docker.service.d')
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'ups-stop.conf').write_text('[Service]\nTimeoutStopSec=15s\n')
        run(['systemctl', 'daemon-reload'], 5)
        run(['systemctl', 'stop', 'docker.socket', 'docker.service'], 25)
        # systemctl uses the admitted mount unit and stops its dependants. No
        # release is sent unless the actual mount has disappeared.
        run(['systemctl', 'stop', 'srv-Media.mount'], 20)
        result = subprocess.run(['findmnt', '-rn', '-M', '/srv/Media'],
                                capture_output=True, timeout=3)
        if result.returncode != 1:
            raise ValueError('NAS mount is still present or cannot be verified')
        if event:
            run([*ssh, f'released {boot} {event}'], 8)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('NAS release not confirmed: ' + type(error).__name__, flush=True)
    finally:
        run(['systemctl', '--no-block', 'poweroff'], 10)


if __name__ == '__main__':
    main()
