"""Native counterpart of the admitted Windows UPS policy; no forced-power tests."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

ALLOWED = set('OL OB LB FSD CHRG DISCHRG RB OVER BYPASS OFF TRIM BOOST ALARM CAL'.split())
ROOT = Path('/var/lib/nas-migration-ups')


def decision(flags, elapsed):
    tokens = set(flags.split()) if flags else set()
    if not tokens or not tokens <= ALLOWED or {'OL', 'OB'} <= tokens:
        return 'unknown'
    if tokens & {'FSD', 'OFF'} or {'OB', 'LB'} <= tokens:
        return 'critical'
    if 'OB' in tokens:
        return 'sustained-battery' if elapsed >= 30 else 'battery-wait'
    if 'OL' in tokens and not tokens & {'LB', 'BYPASS', 'OVER', 'ALARM', 'CAL'}:
        return 'online'
    return 'unknown'


def sample():
    with socket.create_connection(('192.168.50.91', 3493), timeout=2) as sock:
        sock.settimeout(2)
        sock.sendall(b'GET VAR qnapups ups.status\n')
        with sock.makefile('rb') as reader:
            line = reader.readline(513)
    match = re.fullmatch(rb'VAR qnapups ups\.status "([A-Z ]+)"\r?\n', line)
    if not match:
        raise ValueError('Invalid UPS response')
    return match[1].decode('ascii')


def advance(flags, since, now):
    elapsed = max(0, now - since) if since is not None else 0
    outcome = decision(flags, elapsed)
    if outcome == 'online':
        since = None
    elif outcome == 'battery-wait' and since is None:
        since = now
    elif outcome == 'unknown' and since is not None and elapsed >= 30:
        outcome = 'battery-status-lost'
    return outcome, since


def write_state(path, row):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(row, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--observe', action='store_true')
    args = parser.parse_args()
    if args.observe:
        flags = sample()
        print(json.dumps({'status': flags, 'decision': decision(flags, 0), 'shutdownActions': 0}))
        return
    assert os.geteuid() == 0 and socket.gethostname() == 'ben-server'
    ROOT.mkdir(mode=0o700, exist_ok=True)
    with (ROOT / 'guard.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        state_file = ROOT / 'observation.json'
        since = None
        if state_file.exists():
            prior = json.loads(state_file.read_text())
            if prior.get('boot') == boot:
                since = prior.get('batterySinceMonotonic')
        intent = ROOT / 'shutdown-intent.json'
        if intent.exists():
            prior = json.loads(intent.read_text())
            if prior['boot'] == boot or decision(sample(), 0) != 'online':
                raise RuntimeError('Prior shutdown intent requires reconciliation')
            intent.rename(ROOT / ('shutdown-intent-' + prior['boot'] + '.json'))
        while True:
            now = time.monotonic()
            flags = None
            try:
                flags = sample()
            except (OSError, ValueError):
                pass
            outcome, since = advance(flags, since, now)
            row = {'at': time.time(), 'boot': boot, 'status': flags, 'decision': outcome,
                   'batterySinceMonotonic': since}
            write_state(state_file, row)
            if outcome in {'critical', 'sustained-battery', 'battery-status-lost'}:
                with intent.open('x') as stream:
                    json.dump(row, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                # A confirmed outage still requests normal OS shutdown if Docker fails.
                try:
                    listing = subprocess.run(['docker', 'ps', '-q'], capture_output=True, text=True, timeout=5)
                    ids = listing.stdout.split() if listing.returncode == 0 else []
                    assert all(re.fullmatch('[0-9a-f]{12,64}', item) for item in ids)
                    if ids:
                        grace = '10' if outcome == 'critical' else '45'
                        subprocess.run(['docker', 'stop', '--time', grace, *ids], timeout=60, check=True)
                except (OSError, subprocess.SubprocessError, AssertionError) as error:
                    print('Application drain incomplete: ' + type(error).__name__, flush=True)
                subprocess.run(['systemctl', '--no-block', 'poweroff'], timeout=10, check=True)
                return
            time.sleep(5)


if __name__ == '__main__':
    main()
