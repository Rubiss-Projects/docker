"""Exercise the actual Caddy config with local fake Plex and synthetic TLS only."""

import contextlib
import builtins
import fcntl
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Plex(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/upstream-error':
            self.send_response(503)
            self.end_headers()
            return
        if self.path == '/websocket':
            self.send_response(101)
            self.send_header('Connection', 'Upgrade')
            self.send_header('Upgrade', 'websocket')
            self.end_headers()
            return
        if self.path == '/private' and self.headers.get('X-Plex-Token') != 'fixture-token':
            self.send_response(401)
            self.end_headers()
            return
        if self.path == '/range':
            self.send_response(206)
            self.send_header('Content-Range', 'bytes 1-3/6')
            body = b'bcd'
        else:
            self.send_response(200)
            body = json.dumps(dict(self.headers)).encode()
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = os.environ.get('CADDY_BINARY') or shutil.which('caddy')
        if not cls.binary:
            raise RuntimeError('Set CADDY_BINARY to the pinned Caddy binary')
        cls.temp = tempfile.TemporaryDirectory(prefix='caddy-test-')
        cls.root = Path(cls.temp.name)
        cls.https, cls.metrics = free_port(), free_port()
        cls.backend = ThreadingHTTPServer(('127.0.0.1', 0), Plex)
        cls.worker = threading.Thread(target=cls.backend.serve_forever, daemon=True)
        cls.worker.start()
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(cls.root / 'key.pem'), '-out', str(cls.root / 'cert.pem'),
                        '-days', '2', '-subj', '/CN=plex-remote.benlawson.dev',
                        '-addext', 'subjectAltName=DNS:plex-remote.benlawson.dev'],
                       check=True, capture_output=True)
        text = (HERE / 'Caddyfile').read_text()
        # The separate Channels tests own its listener and actual SWAG fixture.
        text = text.replace('import /etc/caddy-plex/channels-lan.caddy', '')
        for old, new in [('192.168.50.40', '127.0.0.1'), ('18443', str(cls.https)),
                         ('19019', str(cls.metrics)), ('127.0.0.1:32400', f'127.0.0.1:{cls.backend.server_port}'),
                         ('/run/caddy-plex/admin.sock', str(cls.root / 'admin.sock')),
                         ('/etc/caddy-plex/tls/current/fullchain.pem', str(cls.root / 'cert.pem')),
                         ('/etc/caddy-plex/tls/current/privkey.pem', str(cls.root / 'key.pem'))]:
            text = text.replace(old, new)
        cls.config = cls.root / 'Caddyfile'
        cls.config.write_text(text)
        cls.output = (cls.root / 'process.log').open('wb')
        cls.process = subprocess.Popen([cls.binary, 'run', '--config', str(cls.config), '--adapter', 'caddyfile'],
                                       stdout=cls.output, stderr=subprocess.STDOUT,
                                       env={**os.environ, 'XDG_DATA_HOME': str(cls.root), 'XDG_CONFIG_HOME': str(cls.root)})
        context = ssl.create_default_context(cafile=str(cls.root / 'cert.pem'))
        for _ in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError((cls.root / 'process.log').read_text())
            try:
                with context.wrap_socket(socket.create_connection(('127.0.0.1', cls.https), 0.2),
                                         server_hostname='plex-remote.benlawson.dev') as probe:
                    probe.sendall(f'GET /healthz HTTP/1.1\r\nHost: plex-remote.benlawson.dev:{cls.https}\r\nConnection: close\r\n\r\n'.encode())
                    if b'200 OK' in probe.recv(1024):
                        break
            except OSError:
                time.sleep(0.05)
        else:
            cls.process.terminate()
            cls.process.wait(timeout=10)
            raise RuntimeError((cls.root / 'process.log').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.output.close()
        cls.backend.shutdown()
        cls.backend.server_close()
        cls.worker.join()
        cls.temp.cleanup()

    def request(self, path, headers=None, method='GET', monitor=False):
        if monitor:
            connection = http.client.HTTPConnection('127.0.0.1', self.metrics, timeout=3)
        else:
            context = ssl.create_default_context(cafile=str(self.root / 'cert.pem'))
            connection = http.client.HTTPSConnection('plex-remote.benlawson.dev', self.https, timeout=3, context=context)
            connection.sock = context.wrap_socket(socket.create_connection(('127.0.0.1', self.https), 3),
                                                  server_hostname='plex-remote.benlawson.dev')
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_spoofed_headers_replaced_and_credentials_preserved(self):
        status, _, body = self.request('/echo', {'X-Forwarded-For': '203.0.113.9', 'X-Real-IP': '203.0.113.9',
                                                 'Forwarded': 'for=203.0.113.9', 'X-Plex-Token': 'fixture-token'})
        headers = {key.lower(): value for key, value in json.loads(body).items()}
        self.assertEqual(status, 200)
        self.assertEqual(headers['x-forwarded-for'], '127.0.0.1')
        self.assertEqual(headers['x-real-ip'], '127.0.0.1')
        self.assertEqual(headers['x-forwarded-proto'], 'https')
        self.assertNotIn('forwarded', headers)
        self.assertEqual(headers['x-plex-token'], 'fixture-token')

    def test_range_and_authentication(self):
        status, headers, body = self.request('/range', {'Range': 'bytes=1-3'})
        self.assertEqual((status, headers.get('Content-Range'), body), (206, 'bytes 1-3/6', b'bcd'))
        self.assertEqual(self.request('/private')[0], 401)
        self.assertEqual(self.request('/private', {'X-Plex-Token': 'fixture-token'})[0], 200)

    def test_websocket_upgrade(self):
        self.assertEqual(self.request('/websocket', {'Connection': 'Upgrade', 'Upgrade': 'websocket'})[0], 101)

    def test_monitoring_is_read_only(self):
        self.assertEqual(self.request('/metrics', monitor=True)[0], 200)
        self.assertEqual(self.request('/reverse_proxy/upstreams', monitor=True)[0], 200)
        for path in ('/config/', '/load', '/stop', '/debug/pprof/', '/reverse_proxy/upstreams/../config/'):
            self.assertEqual(self.request(path, monitor=True)[0], 404)
        self.assertEqual(self.request('/reverse_proxy/upstreams', method='POST', monitor=True)[0], 404)

    def test_error_alert_selects_an_emitted_status_counter(self):
        self.assertEqual(self.request('/upstream-error')[0], 503)
        metrics = self.request('/metrics', monitor=True)[2].decode()
        rules = (HERE.parent / 'grafana/provisioning/alerting/caddy-alert-rules.yaml').read_text()
        expression = rules.split('uid: caddy_http_errors', 1)[1]
        metric = re.search(r'increase\((\w+)\{', expression).group(1)
        handler = re.search(r'handler="([^"]+)"', expression).group(1)
        server = re.search(r'server="([^"]+)"', expression).group(1)
        samples = [line for line in metrics.splitlines() if line.startswith(metric + '{')
                   and 'code="503"' in line and f'handler="{handler}"' in line
                   and f'server="{server}"' in line]
        self.assertTrue(samples, 'The alert must select the actual Caddy 5xx counter')
        self.assertGreaterEqual(float(samples[0].rsplit(' ', 1)[1]), 1)

    def test_health_and_unknown_host(self):
        self.assertEqual(self.request('/healthz')[2], b'ok')
        self.assertEqual(self.request('/identity', {'Host': 'evil.example'})[0], 421)

    def test_certificate_copy_rejects_wrong_host_or_key(self):
        certificate = module('certificate')
        directory = self.root / 'certificate-validation'
        directory.mkdir()
        shutil.copyfile(self.root / 'cert.pem', directory / 'fullchain.pem')
        shutil.copyfile(self.root / 'key.pem', directory / 'privkey.pem')
        certificate.validate(directory)
        with patch.object(certificate, 'HOST', 'wrong.example'):
            with self.assertRaises(ValueError):
                certificate.validate(directory)
        subprocess.run(['openssl', 'genrsa', '-out', str(directory / 'privkey.pem'), '2048'],
                       check=True, capture_output=True)
        with self.assertRaises(ssl.SSLError):
            certificate.validate(directory)


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.health = module('health')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.health.HOLD = Path(self.temp.name) / 'hold'
        self.health.ATTEMPT = Path(self.temp.name) / 'attempt'
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.run = self.stack.enter_context(patch.object(self.health.subprocess, 'run'))
        self.run.return_value = subprocess.CompletedProcess([], 0, 'active\n', '')
        self.stack.enter_context(patch.object(self.health.time, 'sleep'))
        self.probe = self.stack.enter_context(patch.object(self.health, 'healthy', return_value=False))

    def mutations(self):
        return [call.args[0] for call in self.run.call_args_list if 'restart' in call.args[0]]

    def test_held_or_disabled_not_restarted(self):
        self.health.HOLD.touch()
        self.assertEqual(self.health.check(True), 0)
        self.assertFalse(self.mutations())
        self.health.HOLD.unlink()
        self.run.return_value.returncode = 1
        self.assertEqual(self.health.check(True), 0)
        self.assertFalse(self.mutations())

    def test_transient_or_pending_not_restarted(self):
        self.probe.side_effect = [False, True]
        self.assertEqual(self.health.check(True), 0)
        self.assertFalse(self.mutations())
        self.probe.side_effect = None
        self.run.return_value.stdout = 'deactivating\n'
        self.assertEqual(self.health.check(True), 1)
        self.assertFalse(self.mutations())

    def test_cooldown_and_one_scoped_restart(self):
        self.health.ATTEMPT.write_text(str(time.time()))
        self.assertEqual(self.health.check(True), 1)
        self.assertFalse(self.mutations())
        self.health.ATTEMPT.unlink()
        self.probe.side_effect = [False, False, False, True]
        self.assertEqual(self.health.check(True), 0)
        self.assertEqual(self.mutations(), [['systemctl', 'restart', '--no-block', 'caddy-plex.service']])


class KumaPayloadTests(unittest.TestCase):
    def test_creation_and_update_supply_v2_conditions_and_routing(self):
        inner = module('sync-monitor').INNER
        rows = {1: {'id': 1, 'name': 'Infrastructure', 'type': 'group'},
                2: {'id': 2, 'url': 'http://plex:32400/identity', 'notificationIDList': {'7': True, '8': True}}}
        actions = []

        class Client:
            def __init__(self, **_kwargs):
                self.events = {}

            def on(self, event, callback):
                self.events[event] = callback

            def connect(self, *_args, **_kwargs):
                self.events['info']({})

            def call(self, event, data, **_kwargs):
                if event == 'login':
                    self.events['notificationList']([
                        {'id': 7, 'config': '{"type":"discord"}'},
                        {'id': 8, 'config': '{"type":"webhook"}'}])
                if event == 'getMonitorList':
                    self.events['monitorList'](rows)
                if event in ('add', 'editMonitor'):
                    if data.get('conditions') != []:
                        raise ValueError('Kuma v2 monitor.conditions is required')
                    actions.append((event, data))
                    ident = data.get('id', max(rows) + 1)
                    rows[ident] = {**data, 'id': ident}
                    return {'ok': True, 'monitorID': ident}
                return {'ok': True}

            def disconnect(self):
                pass

        with patch.dict('sys.modules', {'socketio': SimpleNamespace(Client=Client)}), \
             patch.dict(os.environ, {'UPTIME_KUMA_URL': 'http://fixture.invalid',
                                    'UPTIME_KUMA_USERNAME': 'fixture', 'UPTIME_KUMA_PASSWORD': 'fixture'}):
            exec(inner, {})
            exec(inner, {})
        self.assertEqual([action for action, _ in actions], ['add', 'add', 'editMonitor', 'editMonitor'])
        for _, data in actions:
            self.assertEqual(data['notificationIDList'], {'7': True})
            self.assertEqual(data['parent'], 1)
            self.assertFalse(data['ignoreTls'])
            self.assertEqual(data['expiryNotification'], data['name'] == 'caddy')


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.install = module('install')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_interrupted_write_preserves_destination_and_next_install_succeeds(self):
        destination = self.root / 'config'
        destination.write_bytes(b'original')
        stale = self.root / 'config.new'
        stale.write_bytes(b'retained incomplete prior candidate')
        with patch.object(self.install.os, 'fchown'), patch.object(Path, 'replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.install.install_file(destination, b'new', 0o640, 0)
        self.assertEqual(destination.read_bytes(), b'original')
        self.assertEqual(set(self.root.iterdir()), {destination, stale})
        with patch.object(self.install.os, 'fchown'):
            self.install.install_file(destination, b'new', 0o640, 0)
        self.assertEqual(destination.read_bytes(), b'new')
        self.assertEqual(stale.read_bytes(), b'retained incomplete prior candidate')
        self.assertEqual(destination.stat().st_mode & 0o777, 0o640)

    def test_publication_excludes_helpers_through_validation_and_daemon_reload(self):
        destination = self.root / 'config'
        destination.write_bytes(b'original')
        backup = self.root / 'backup'
        backup.mkdir()
        lock_path = self.root / 'operation.lock'
        phases = []
        real_open = builtins.open

        def open_lock(path, *args, **kwargs):
            return real_open(lock_path if path == '/run/lock/caddy-plex.lock' else path, *args, **kwargs)

        def assert_locked():
            with real_open(lock_path, 'a') as other:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(destination.read_bytes(), b'new')

        def sync(**kwargs):
            assert_locked()
            self.assertEqual(kwargs, {'reload_active': False})
            phases.append('certificate')

        def run(*args):
            assert_locked()
            phases.append(args[1])

        with patch.object(builtins, 'open', side_effect=open_lock), \
             patch.object(self.install.os, 'fchown'), \
             patch.object(self.install.subprocess, 'run', return_value=subprocess.CompletedProcess([], 3)), \
             patch.object(self.install.runpy, 'run_path', return_value={'sync': sync}), \
             patch.object(self.install, 'run', side_effect=run):
            self.install.publish({destination: (b'new', 0o640, 0)}, backup)
        self.assertEqual(phases, ['certificate', 'validate', 'exec', 'exec', 'daemon-reload'])
        self.assertEqual((backup / 'config').read_bytes(), b'original')
        with real_open(lock_path, 'a') as other:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)


if __name__ == '__main__':
    unittest.main()
