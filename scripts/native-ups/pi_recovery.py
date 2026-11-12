"""Wake previously reachable computers after a UPS outage; never control power outlets.

The Pi owns the USB collector. Start in observe mode until the handoff and each
computer's wake test have passed. Unknown UPS data never permits a wake packet.
"""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import time

from native_ups_guard import decision, require_local_nut_listener, write_state

ROOT = Path('/var/lib/ups-pi-recovery')
HOSTS = {'ben-server': ('192.168.50.40', '58:d8:12:91:1c:89'),
         'ben-pc': ('192.168.50.209', '58:11:22:bb:86:30')}
STABLE_SECONDS = 180
MIN_CHARGE = 50
MAX_ATTEMPTS = 5


def read_ups():
    """Use one verified local NUT connection for fresh status and battery charge."""
    owner = require_local_nut_listener()
    values = {}
    with socket.create_connection(('127.0.0.1', 3493), timeout=2) as sock:
        sock.settimeout(2)
        with sock.makefile('rb') as stream:
            for field in ('ups.status', 'battery.charge'):
                sock.sendall(f'GET VAR qnapups {field}\n'.encode('ascii'))
                line = stream.readline(513).decode('ascii').rstrip('\r\n')
                prefix = f'VAR qnapups {field} "'
                if not line.startswith(prefix) or not line.endswith('"'):
                    raise ValueError('UPS status unavailable')
                values[field] = line[len(prefix):-1]
    if require_local_nut_listener() != owner:
        raise ValueError('UPS listener changed')
    charge = float(values['battery.charge'])
    if not math.isfinite(charge) or not 0 <= charge <= 100:
        raise ValueError('Invalid battery charge')
    return values['ups.status'], charge


def transition(state, flags, charge, reachable, now):
    """Pure policy transition. Times are monotonic and reset on process startup.

Only hosts seen online in the preceding 20 seconds become outage candidates.
Pending candidates survive collector restarts, but the stability timer does not.
A running host is removed only after the stable recovery interval, allowing its
already-committed shutdown to finish even if mains returns during the drain.
"""
    outcome = decision(flags, 0)
    pending = state.setdefault('pending', {})
    seen = state.setdefault('seen', {})
    if outcome in {'battery-wait', 'critical'}:
        state['onlineSince'] = None
        if not state.get('outage'):
            state['outage'] = True
            for name, last in seen.items():
                if name in HOSTS and now - last <= 20:
                    pending.setdefault(name, {'attempts': 0, 'lastAttempt': None})
    elif outcome != 'online':
        state['onlineSince'] = None
    else:
        if state.get('onlineSince') is None:
            state['onlineSince'] = now
        stable = now - state['onlineSince'] >= STABLE_SECONDS
        if stable:
            state['outage'] = False
            for name in reachable:
                pending.pop(name, None)
        # Refresh the pre-outage inventory only outside an unsettled outage.
        if not state.get('outage'):
            for name in reachable:
                seen[name] = now
        if stable and charge >= MIN_CHARGE:
            return [name for name, row in pending.items()
                    if name not in reachable and row['attempts'] < MAX_ATTEMPTS
                    and (row['lastAttempt'] is None or now - row['lastAttempt'] >= 60)]
    return []


def reachable_hosts():
    return {name for name, (ip, _) in HOSTS.items()
            if subprocess.run(['ping', '-n', '-c', '1', '-W', '1', ip],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=3).returncode == 0}


def wake(name):
    mac = bytes.fromhex(HOSTS[name][1].replace(':', ''))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('192.168.50.216', 0))
        sock.sendto(b'\xff' * 6 + mac * 16, ('192.168.50.255', 9))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--enable-wake', action='store_true')
    args = parser.parse_args()
    if socket.gethostname() != 'ben-pi' or os.geteuid() != 0:
        raise ValueError('Recovery is restricted to the admitted Pi')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    lock = (ROOT / 'recovery.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    path = ROOT / 'state.json'
    state = json.loads(path.read_text()) if path.exists() else {'pending': {}}
    if set(state.get('pending', {})) - HOSTS.keys():
        raise ValueError('Unknown recovery target')
    # A restart never trusts an old reachability sample or an old stability timer.
    state.update(seen={}, onlineSince=None)
    for row in state['pending'].values():
        row['lastAttempt'] = None
    while True:
        flags, charge = None, 0
        try:
            flags, charge = read_ups()
        except (OSError, ValueError):
            pass
        now = time.monotonic()
        reachable = reachable_hosts()
        targets = transition(state, flags, charge, reachable, now)
        state.update(at=time.time(), status=flags, charge=charge,
                     reachable=sorted(reachable), wouldWake=targets,
                     wakeEnabled=args.enable_wake)
        write_state(path, state)
        if args.enable_wake:
            for name in targets:
                # Recheck power immediately before every side effect.
                try:
                    current, battery = read_ups()
                    if decision(current, 0) != 'online' or battery < MIN_CHARGE:
                        state['onlineSince'] = None
                        break
                    state['pending'][name]['attempts'] += 1
                    state['pending'][name]['lastAttempt'] = now
                    write_state(path, state)
                    wake(name)
                    print(f'Wake packet sent to {name}', flush=True)
                except (OSError, ValueError) as error:
                    state['onlineSince'] = None
                    print(f'Wake held: {type(error).__name__}', flush=True)
                    break
        time.sleep(5)


if __name__ == '__main__':
    main()
