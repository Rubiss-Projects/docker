#!/usr/bin/env python3
"""Short-deadline, read-only host telemetry; failure never initiates recovery."""
import argparse
import fcntl
import runpy
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
import urllib.error

spec = importlib.util.spec_from_file_location('retained_rpc', Path(__file__).with_name('rpc-health.py'))
rpc_probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rpc_probe)
rpc_probe.MAX_RESPONSE = 64 * 1024


class DeadlineExceeded(TimeoutError):
    pass


def sample(url='http://127.0.0.1:9091/transmission/rpc', deadline_seconds=3):
    """Measure token negotiation, full response and validation against one monotonic deadline."""
    started = time.monotonic()
    result = {'rpc_up': 0, 'deadline_exceeded': 0, 'slow': 0, 'failure_code': 0}
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expire(_signal, _frame):
        raise DeadlineExceeded()

    signal.signal(signal.SIGALRM, expire)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, deadline_seconds)
    try:
        response = rpc_probe.RPC(url, timeout=deadline_seconds).call('session-stats')
        for field in ['torrentCount', 'activeTorrentCount', 'pausedTorrentCount', 'downloadSpeed', 'uploadSpeed']:
            rpc_probe.number(response[field])
        elapsed = time.monotonic() - started
        result.update(rpc_up=1, rpc_seconds=elapsed, slow=int(elapsed > 1))
    except (DeadlineExceeded, socket.timeout):
        result.update(deadline_exceeded=1, failure_code=2)
    except urllib.error.URLError as error:
        timed_out = isinstance(error.reason, TimeoutError)
        result.update(deadline_exceeded=int(timed_out), failure_code=2 if timed_out else 1)
    except rpc_probe.ProbeError as error:
        reason = str(error)
        result['failure_code'] = 3 if reason.startswith('http_') else 5 if reason == 'session_negotiation_failed' else 1 if reason == 'response_too_large' else 4
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        result['failure_code'] = 4
    except Exception:
        result['failure_code'] = 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(0.001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1])
    result.update(attempt_seconds=time.monotonic() - started, observed_at=int(time.time()))
    return result


def line_protocol(values):
    fields = ','.join(f'{key}={value}i' if isinstance(value, int) else f'{key}={value}' for key, value in values.items())
    return 'transmission_host_rpc,service=transmission,observer=native_linux ' + fields


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate", action="store_true", help="Run the retained 30-second inventory probe")
    args = parser.parse_args()
    if args.aggregate:
        os.environ.update(json.loads(Path("/etc/telegraf/transmission-rpc-credentials.json").read_text()))
        sys.argv = ["rpc-health.py", "--metrics"]
        runpy.run_path(str(Path(__file__).with_name("rpc-health.py")), run_name="__main__")
        return 0
    # Overlap is missing telemetry, not another RPC request or an invented failure sample.
    with open('/tmp/transmission-native-host-rpc.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 1
        os.environ.update(json.loads(Path('/etc/telegraf/transmission-rpc-credentials.json').read_text()))
        values = sample()
        print(line_protocol(values))
    return 0


if __name__ == '__main__':
    sys.exit(main())
