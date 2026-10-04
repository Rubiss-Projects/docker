"""Actual Caddy + nginx, synthetic backend/TLS/key, no production mounts or data."""

import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
import uuid

from test_caddy import free_port, module

HERE = Path(__file__).resolve().parent
KEY = 'a1' * 32
HOST = 'channels-lan-relay.benlawson.dev'


class ChannelsProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = os.environ['CADDY_BINARY']
        image = os.environ.get('NGINX_TEST_IMAGE')
        if not image:
            raise RuntimeError('Set NGINX_TEST_IMAGE to the installed SWAG image ID; never pull a test image')
        cls.temp = tempfile.TemporaryDirectory(prefix='channels-proxy-test-', dir=Path.home())
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        # Desktop's Windows host can reserve ephemeral ranges that Linux bind(0)
        # considers free. Use an explicit low loopback fixture port instead.
        cls.port, cls.tls_port = free_port(), int(os.environ.get('NGINX_TEST_PORT', '18092'))
        cls.metrics = free_port()
        (cls.root / 'private').mkdir()
        (cls.root / 'private/key.conf').write_text(f'~^{KEY}$ 1;\n')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(cls.root / 'key.pem'), '-out', str(cls.root / 'cert.pem'),
                        '-days', '2', '-subj', f'/CN={HOST}', '-addext', f'subjectAltName=DNS:{HOST}'],
                       check=True, capture_output=True)
        relay = (HERE.parent / 'swag/config/nginx/proxy-confs/channels-lan-relay.subdomain.conf').read_text()
        relay = relay.replace('listen 443 ssl;', 'listen 8443 ssl;').replace('listen [::]:443 ssl;', '')
        relay = relay.replace('include /config/nginx/ssl.conf;',
                              'ssl_certificate /fixture/cert.pem; ssl_certificate_key /fixture/key.pem;')
        relay = relay.replace('/config/nginx/channels-lan-private', '/fixture/private')
        relay = relay.replace('include /config/nginx/resolver.conf;', 'resolver 127.0.0.11;')
        relay = relay.replace('channels-dvr:8089', '127.0.0.1:8089')
        backend = r'''
        server {
            listen 127.0.0.1:8089;
            location /range { add_header Content-Range 'bytes 1-3/6'; return 206 'bcd'; }
            location /websocket {
                add_header Upgrade websocket always; add_header Connection Upgrade always; return 101;
            }
            location /fail { return 503; }
            location / {
                default_type application/json;
                return 200 '{"method":"$request_method","key":"$http_x_channels_lan_key","xff":"$http_x_forwarded_for","real":"$http_x_real_ip","forwarded":"$http_forwarded","skip":"$http_x_dvr_skipauth","force":"$http_x_dvr_forceauth","authorization":"$http_authorization"}';
            }
        }
        '''
        config = ('pid /tmp/nginx.pid; error_log /dev/stderr; events {} http { access_log off; '
                  'client_body_temp_path /tmp/client; proxy_temp_path /tmp/proxy; '
                  'fastcgi_temp_path /tmp/fastcgi; uwsgi_temp_path /tmp/uwsgi; scgi_temp_path /tmp/scgi; '
                  'map $http_upgrade $connection_upgrade { default upgrade; "" close; }\n' + relay + backend + '}')
        (cls.root / 'nginx.conf').write_text(config)
        name = 'channels-swag-fixture-' + uuid.uuid4().hex[:10]
        created = subprocess.run(['docker', 'run', '--detach', '--pull=never', '--name', name,
                                  '--cidfile', str(cls.root / 'container.id'),
                                  '--user', f'{os.getuid()}:{os.getgid()}',
                                  '--read-only', '--tmpfs', '/tmp:rw,size=16m', '--cap-drop=ALL',
                                  '--security-opt=no-new-privileges:true', '--memory=96m', '--pids-limit=32',
                                  '--restart=no', '--publish', f'127.0.0.1:{cls.tls_port}:8443',
                                  '--mount', f'type=bind,src={cls.root},dst=/fixture,readonly',
                                  '--entrypoint', 'nginx', image, '-e', '/dev/stderr', '-c', '/fixture/nginx.conf', '-g', 'daemon off;'],
                                 capture_output=True, text=True, timeout=30)
        if (cls.root / 'container.id').exists():
            cls.container = (cls.root / 'container.id').read_text().strip()
            cls.addClassCleanup(cls.remove_container)
        if created.returncode:
            raise RuntimeError('Synthetic nginx launch failed: ' + created.stderr)
        # Isolated addresses/ports are the only runtime substitutions; predicates
        # and both production proxy bodies stay intact.
        native = (HERE / 'channels-lan.caddy').read_text()
        native = native.replace('bind 192.168.50.40 127.0.0.1', 'bind 127.0.0.1 ::1')
        native = native.replace('192.168.50.40', '127.0.0.1').replace('192.168.50.0/24', '127.0.0.1/32')
        native = native.replace(':18089', f':{cls.port}').replace('127.0.0.1:443', f'127.0.0.1:{cls.tls_port}')
        native = native.replace('@CHANNELS_LAN_KEY@', KEY).replace(
            'tls_server_name ' + HOST, 'tls_server_name ' + HOST + '\n tls_trust_pool file ' + str(cls.root / 'cert.pem'))
        (cls.root / 'Caddyfile').write_text('''{
            admin off
            auto_https off
            persist_config off
            metrics
            servers @LISTEN@ {
                name channels_lan
            }
            log default {
                exclude http.log.access http.log.error
            }
        }
        '''.replace('@LISTEN@', f'127.0.0.1:{cls.port}') + native +
            f'\nhttp://127.0.0.1:{cls.metrics} {{\n metrics /metrics\n}}\n')
        cls.output = (cls.root / 'caddy.log').open('wb')
        cls.addClassCleanup(cls.output.close)
        cls.process = subprocess.Popen([cls.binary, 'run', '--config', str(cls.root / 'Caddyfile'), '--adapter', 'caddyfile'],
                                       stdout=cls.output, stderr=subprocess.STDOUT,
                                       env={**os.environ, 'XDG_DATA_HOME': str(cls.root), 'XDG_CONFIG_HOME': str(cls.root)})
        cls.addClassCleanup(cls.stop_caddy)
        for _ in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError((cls.root / 'caddy.log').read_text())
            try:
                if cls.request('/status')[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError('Synthetic proxy did not become ready: ' +
                               subprocess.run(['docker', 'logs', cls.container], capture_output=True, text=True).stderr +
                               (cls.root / 'caddy.log').read_text())

    @classmethod
    def remove_container(cls):
        subprocess.run(['docker', 'stop', '--time', '10', cls.container], check=True, capture_output=True, timeout=20)
        subprocess.run(['docker', 'rm', cls.container], check=True, capture_output=True, timeout=10)

    @classmethod
    def stop_caddy(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)

    @classmethod
    def request(cls, path, headers=None, method='GET', source='127.0.0.1', relay=False):
        if relay:
            context = ssl.create_default_context(cafile=str(cls.root / 'cert.pem'))
            connection = http.client.HTTPSConnection(HOST, timeout=3, context=context)
            connection.sock = context.wrap_socket(socket.create_connection(('127.0.0.1', cls.tls_port), 3), server_hostname=HOST)
        else:
            address = '::1' if source == '::1' else '127.0.0.1'
            connection = http.client.HTTPConnection(address, cls.port, timeout=3, source_address=(source, 0))
            headers = {'Host': '127.0.0.1', **(headers or {})}
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_direct_relay_rejects_missing_wrong_and_combined_keys(self):
        for key in (None, 'wrong', KEY.upper(), KEY + ', ' + KEY):
            headers = {} if key is None else {'X-Channels-Lan-Key': key}
            headers.update({'X-Forwarded-For': '192.168.50.10', 'X-DVR-SkipAuth': 'true'})
            self.assertEqual(self.request('/status', headers, relay=True)[0], 403)

    def test_native_gate_uses_peer_and_host_not_claimed_forwarded_address(self):
        # WSL folds IPv4 loopback peers to 127.0.0.1. IPv6 loopback is a distinct
        # actual peer outside this fixture's allowed 127.0.0.1/32 network.
        self.assertEqual(self.request('/status', {'X-Forwarded-For': '127.0.0.1'}, source='::1')[0], 403)
        self.assertEqual(self.request('/status', {'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('/healthz', source='127.0.0.2')[0], 200)

    def test_relay_strips_private_and_identity_headers_but_preserves_app_auth(self):
        status, _, body = self.request('/status', {
            'X-Channels-Lan-Key': 'spoofed', 'Forwarded': 'for=203.0.113.1', 'X-Forwarded-For': '203.0.113.1',
            'X-Real-IP': '203.0.113.1', 'X-DVR-SkipAuth': 'true', 'X-DVR-ForceAuth': 'true',
            'Authorization': 'Bearer synthetic-app-token'})
        self.assertEqual(status, 200)
        received = json.loads(body)
        self.assertEqual({k: received[k] for k in ('key', 'xff', 'real', 'forwarded', 'skip', 'force')},
                         dict.fromkeys(('key', 'xff', 'real', 'forwarded', 'skip', 'force'), ''))
        self.assertEqual(received['authorization'], 'Bearer synthetic-app-token')

    def test_app_methods_ranges_and_websocket(self):
        self.assertEqual(json.loads(self.request('/echo', method='POST')[2])['method'], 'POST')
        status, headers, body = self.request('/range', {'Range': 'bytes=1-3'})
        self.assertEqual((status, headers['Content-Range'], body), (206, 'bytes 1-3/6', b'bcd'))
        self.assertEqual(self.request('/websocket', {'Connection': 'Upgrade', 'Upgrade': 'websocket'})[0], 101)
        self.assertEqual(self.request('/fail')[0], 503)

    def test_alerts_select_actual_upstream_and_status_metrics(self):
        import re
        self.assertEqual(self.request('/fail')[0], 503)
        connection = http.client.HTTPConnection('127.0.0.1', self.metrics, timeout=3)
        try:
            connection.request('GET', '/metrics')
            metrics = connection.getresponse().read().decode()
        finally:
            connection.close()
        rules = (HERE.parent / 'grafana/provisioning/alerting/caddy-alert-rules.yaml').read_text()
        rule = rules.split('uid: caddy_channels_http_errors', 1)[1]
        metric = re.search(r'increase\((\w+)\{', rule)[1]
        self.assertTrue(any(line.startswith(metric + '{') and 'code="503"' in line and
                            'server="channels_lan"' in line and 'handler="subroute"' in line
                            for line in metrics.splitlines()))
        self.assertIn(f'caddy_reverse_proxy_upstreams_healthy{{upstream="127.0.0.1:{self.tls_port}"}} 1', metrics)

    def test_z_missing_key_denies_every_request(self):
        key = self.root / 'private/key.conf'
        inactive = key.with_suffix('.disabled')
        key.rename(inactive)
        try:
            subprocess.run(['docker', 'exec', self.container, 'nginx', '-e', '/dev/stderr',
                            '-c', '/fixture/nginx.conf', '-s', 'reload'], check=True, capture_output=True, timeout=5)
            for _ in range(40):
                status = self.request('/status', {'X-Channels-Lan-Key': KEY}, relay=True)[0]
                if status == 403:
                    break
                time.sleep(.05)
            self.assertEqual(status, 403)
        finally:
            inactive.rename(key)


class SecretRenderingTests(unittest.TestCase):
    def test_unusable_key_refuses_rendering(self):
        from unittest.mock import patch
        installer = module('install')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'channels-lan.caddy').write_bytes((HERE / 'channels-lan.caddy').read_bytes())
            with patch.object(installer, 'SOURCE', root):
                for value in ('', 'CHANNELS_LAN_KEY=', 'CHANNELS_LAN_KEY=x\nserver evil', '\x00GITCRYPT'):
                    (root / 'channels-lan.env.secret').write_text(value)
                    with self.assertRaises(ValueError):
                        installer.channels_config()
                (root / 'channels-lan.env.secret').write_text('CHANNELS_LAN_KEY=' + KEY)
                native, guard = installer.channels_config()
                self.assertNotIn(b'@CHANNELS_LAN_KEY@', native)
                self.assertEqual(guard, f'~^{KEY}$ 1;\n'.encode())
