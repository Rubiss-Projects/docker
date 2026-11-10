import importlib.util
import json
from pathlib import Path
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec = importlib.util.spec_from_file_location('native_host_probe', Path(__file__).with_name('native-host-rpc.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class NativeHostProbeTests(unittest.TestCase):
    def test_existing_influx_integer_field_types_are_preserved(self):
        line = probe.line_protocol({'rpc_up': 1, 'failure_code': 0, 'deadline_exceeded': 0, 'slow': 0, 'observed_at': 1794300000, 'attempt_seconds': 0.02, 'rpc_seconds': 0.02})
        fields = dict(item.split('=', 1) for item in line.split(' ', 1)[1].split(','))
        for key in ['rpc_up', 'failure_code', 'deadline_exceeded', 'slow', 'observed_at']:
            self.assertTrue(fields[key].endswith('i'))
        self.assertFalse(fields['attempt_seconds'].endswith('i'))
        self.assertFalse(fields['rpc_seconds'].endswith('i'))

    def server(self, mode):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(request['method'])
                if mode == 'unauthorized':
                    self.send_response(401)
                    self.end_headers()
                    return
                if self.headers.get('X-Transmission-Session-Id') != 'test-token' or mode == 'challenge-loop':
                    self.send_response(409)
                    self.send_header('X-Transmission-Session-Id', 'test-token')
                    self.end_headers()
                    return
                data = {'torrentCount': 1557, 'activeTorrentCount': 5, 'pausedTorrentCount': 0, 'downloadSpeed': 20, 'uploadSpeed': 50}
                if mode == 'missing-field':
                    del data['torrentCount']
                if mode == 'invalid-number':
                    data['torrentCount'] = True
                body = json.dumps({'result': 'failure' if mode == 'rpc-failure' else 'success', 'arguments': data}).encode()
                if mode == 'invalid-json':
                    body = b'not json'
                if mode == 'oversized':
                    body = b' ' * (65536 + 1)
                self.send_response(200)
                self.end_headers()
                try:
                    if mode == 'trickle':
                        for _ in range(100):
                            self.wfile.write(b' ')
                            self.wfile.flush()
                            time.sleep(0.01)
                    else:
                        self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}/transmission/rpc', calls

    def test_success_negotiates_and_only_reads_session_stats(self):
        url, calls = self.server('healthy')
        result = probe.sample(url, 0.5)
        self.assertEqual(result['rpc_up'], 1)
        self.assertEqual(result['failure_code'], 0)
        self.assertIn('rpc_seconds', result)
        self.assertTrue(calls)
        self.assertEqual(set(calls), {'session-stats'})

    def test_failed_samples_never_enter_success_percentiles(self):
        for mode, expected in [('unauthorized', 3), ('challenge-loop', 5), ('missing-field', 4), ('invalid-number', 4), ('invalid-json', 4), ('rpc-failure', 4), ('oversized', 1)]:
            with self.subTest(mode=mode):
                url, calls = self.server(mode)
                result = probe.sample(url, 0.5)
                self.assertEqual(result['rpc_up'], 0)
                self.assertEqual(result['failure_code'], expected)
                self.assertNotIn('rpc_seconds', result)
                self.assertEqual(set(calls), {'session-stats'})

    def test_absolute_deadline_covers_a_trickling_body(self):
        url, _ = self.server('trickle')
        started = time.monotonic()
        result = probe.sample(url, 0.08)
        self.assertLess(time.monotonic() - started, 0.3)
        self.assertEqual(result['deadline_exceeded'], 1)
        self.assertEqual(result['failure_code'], 2)
        self.assertNotIn('rpc_seconds', result)


if __name__ == '__main__':
    unittest.main()
