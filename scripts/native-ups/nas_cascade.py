"""Authenticated NAS shutdown coordination; no fixed delay after storage release."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from native_ups_guard import decision, write_state

ROOT = Path('/var/lib/ups-pi-recovery')
SSH_CONFIG = '/etc/ups-cascade/ssh_config'
# A failed server drain cannot consume the entire UPS. This is a failure ceiling,
# not an extra delay on the successful path. QNAP retains its own UPS fallback.
FAILURE_SECONDS = 180


def remote(command):
    result = subprocess.run(['ssh', '-F', SSH_CONFIG, 'nas', command],
                            capture_output=True, text=True, timeout=8, check=True)
    return json.loads(result.stdout)


def nas_status():
    try:
        row = remote('status')
        if (not re.fullmatch('[0-9a-f-]{36}', row['boot'])
                or type(row['ready']) is not bool):
            raise ValueError('Invalid NAS status')
        return row
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return None


def cascade(state, flags, reachable, nas, receipt, now):
    """Return a shutdown reason only for the NAS boot recorded in this outage.

    A short outage cancels before commitment. After a confirmed server release,
    returning utility power does not abandon the already committed cascade.
    Unknown UPS status alone never admits a NAS shutdown.
    """
    outcome = decision(flags, 0)
    event = state.get('cascade')
    matching = bool(event and receipt and receipt.get('event') == event['id'])
    released = matching and receipt.get('phase') == 'released'
    if event and outcome == 'online' and not released and not event['requested']:
        event.setdefault('returned', now)
        if nas:
            state['nasSeen'] = {'boot': nas['boot'], 'at': now}
        if now - event['returned'] >= 180:
            state.pop('cascade')
            return None
    if (event and outcome in {'battery-wait', 'critical'} and 'returned' in event
            and not matching and not event['requested']):
        state.pop('cascade')
        event = None
    if event is None:
        if outcome in {'battery-wait', 'critical'}:
            previous = state.get('nasSeen')
            if previous and 0 <= now - previous['at'] <= 20:
                event = {'id': str(uuid.uuid4()), 'started': now,
                         'nasBoot': previous['boot'], 'requested': False}
                state['cascade'] = event
                state.setdefault('pending', {}).setdefault('nas',
                    {'attempts': 0, 'lastAttempt': None, 'observedOffline': 'nas' not in reachable})
        elif outcome == 'online' and nas:
            state['nasSeen'] = {'boot': nas['boot'], 'at': now}
        if event is None:
            return None
    released = (receipt is not None and receipt.get('event') == event['id']
                and receipt.get('phase') == 'released')
    if nas and nas['boot'] != event['nasBoot']:
        # Never shut down a recovered NAS using the previous boot's intent.
        event['recovered'] = True
        return None
    if event.get('recovered') or event['requested']:
        return None
    if outcome == 'online' and not released:
        # Keep the event briefly for a server that committed at the same moment
        # utility returned. Only an authenticated release can finish it online.
        return None
    if released and 'ben-server' not in reachable:
        return 'server-storage-released'
    if outcome == 'critical':
        return 'critical-battery'
    if outcome == 'battery-wait' and now - event['started'] >= FAILURE_SECONDS:
        return 'server-drain-timeout'
    return None


def receive():
    """Root-only SSH forced command for the server's dedicated reporting key.

    No shell or arbitrary paths are accepted. The release must match both the
    Pi's current outage UUID and the server boot that began the handshake.
    """
    if os.geteuid() != 0:
        raise ValueError('Root receiver required')
    command = sys.argv[1] if len(sys.argv) == 2 else os.environ.get('SSH_ORIGINAL_COMMAND', '')
    words = command.split()
    if len(words) not in {2, 3} or words[0] not in {'begin', 'released'}:
        raise ValueError('Invalid report')
    boot = str(uuid.UUID(words[1]))
    state = json.loads((ROOT / 'state.json').read_text())
    event = state.get('cascade')
    if not event or event.get('recovered') or event.get('requested'):
        raise ValueError('No active NAS cascade')
    path = ROOT / 'server-release.json'
    if words[0] == 'begin' and len(words) == 2:
        write_state(path, {'event': event['id'], 'boot': boot, 'phase': 'begin'})
        print(event['id'])
    elif words[0] == 'released' and len(words) == 3:
        prior = json.loads(path.read_text())
        if prior != {'event': words[2], 'boot': boot, 'phase': 'begin'} or words[2] != event['id']:
            raise ValueError('Release does not match active handshake')
        write_state(path, {**prior, 'phase': 'released', 'at': time.time()})
        print('accepted')
    else:
        raise ValueError('Invalid phase')


if __name__ == '__main__':
    receive()
