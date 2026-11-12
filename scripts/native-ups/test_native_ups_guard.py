import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
import native_ups_guard as guard
from native_ups_guard import advance, decision


class PowerDecisionTests(unittest.TestCase):
    def test_handoff_endpoint_selects_only_admitted_hosts(self):
        for host in ['192.168.50.91', '192.168.50.216', '127.0.0.1']:
            with self.subTest(host=host), patch.dict(guard.os.environ, {'NATIVE_UPS_HOST': host}), \
                    patch.object(guard, 'require_local_nut_listener', return_value=('100', '200')), \
                    patch.object(guard, 'verified_pi_tls', side_effect=lambda sock: sock), \
                    patch.object(guard.socket, 'create_connection') as connect:
                socket = connect.return_value.__enter__.return_value
                reader = socket.makefile.return_value.__enter__.return_value
                reader.readline.return_value = b'VAR qnapups ups.status "OL CHRG"\n'
                self.assertEqual(guard.sample(), 'OL CHRG')
                connect.assert_called_once_with((host, 3493), timeout=2)

    def test_pi_rejects_plaintext_and_never_queries_shutdown_status(self):
        with patch.dict(guard.os.environ, {'NATIVE_UPS_HOST': guard.PI_HOST}), \
                patch.object(guard.ssl, 'create_default_context'), \
                patch.object(guard.socket, 'create_connection') as connect:
            sock = connect.return_value.__enter__.return_value
            sock.recv.side_effect = [bytes([byte]) for byte in b'ERR FEATURE-NOT-SUPPORTED\n']
            with self.assertRaisesRegex(ValueError, 'verified TLS'):
                guard.sample()
            sock.sendall.assert_called_once_with(b'STARTTLS\n')
            sock.makefile.assert_not_called()

    def test_pi_requires_dedicated_ca_and_matching_certificate(self):
        with patch.dict(guard.os.environ, {'NATIVE_UPS_HOST': guard.PI_HOST}), \
                patch.object(guard.ssl, 'create_default_context') as create_context, \
                patch.object(guard.socket, 'create_connection') as connect:
            sock = connect.return_value.__enter__.return_value
            sock.recv.side_effect = [bytes([byte]) for byte in b'OK STARTTLS\n']
            context = create_context.return_value
            context.wrap_socket.side_effect = guard.ssl.SSLCertVerificationError('untrusted peer')
            with self.assertRaises(guard.ssl.SSLCertVerificationError):
                guard.sample()
            create_context.assert_called_once_with(cafile=guard.PI_CA)
            context.wrap_socket.assert_called_once_with(sock, server_hostname=guard.PI_HOST)
            self.assertEqual(context.minimum_version, guard.ssl.TLSVersion.TLSv1_2)
            sock.sendall.assert_called_once_with(b'STARTTLS\n')
            sock.makefile.assert_not_called()

    def test_unadmitted_endpoint_fails_before_connecting(self):
        with patch.dict(guard.os.environ, {'NATIVE_UPS_HOST': 'example.invalid'}), \
                patch.object(guard.socket, 'create_connection') as connect:
            with self.assertRaises(ValueError):
                guard.sample()
            connect.assert_not_called()

    def test_unprivileged_loopback_responder_is_rejected_when_nut_is_stopped(self):
        with patch.dict(guard.os.environ, {'NATIVE_UPS_HOST': '127.0.0.1'}), \
                patch.object(guard.subprocess, 'check_output', return_value='ActiveState=inactive\nMainPID=0\n'), \
                patch.object(guard.socket, 'create_connection') as connect:
            with self.assertRaisesRegex(ValueError, 'not active'):
                guard.sample()
            connect.assert_not_called()

    def test_listener_must_belong_to_systemds_nut_main_process(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(guard, 'PROC', Path(folder)), \
                patch.object(guard.subprocess, 'check_output', return_value='ActiveState=active\nMainPID=100\n'):
            proc = Path(folder);(proc/'net').mkdir();(proc/'100/fd').mkdir(parents=True)
            (proc/'net/tcp').write_text('header\n0: 0100007F:0DA5 00000000:0000 0A 0:0 0:0 0 999 0 200\n')
            (proc/'100/fd/3').symlink_to('socket:[201]')
            with self.assertRaisesRegex(ValueError, 'does not belong'):
                guard.require_local_nut_listener()
            (proc/'100/fd/3').unlink();(proc/'100/fd/3').symlink_to('socket:[200]')
            self.assertEqual(guard.require_local_nut_listener(), ('100', '200'))

    def test_replaced_listener_cannot_supply_a_critical_status(self):
        with patch.dict(guard.os.environ, {'NATIVE_UPS_HOST': '127.0.0.1'}), \
                patch.object(guard, 'require_local_nut_listener', side_effect=[('100', '200'), ('101', '201')]), \
                patch.object(guard.socket, 'create_connection') as connect:
            socket = connect.return_value.__enter__.return_value
            socket.makefile.return_value.__enter__.return_value.readline.return_value = b'VAR qnapups ups.status "FSD"\n'
            with self.assertRaisesRegex(ValueError, 'changed during'):
                guard.sample()

    def test_admitted_policy_cases(self):
        cases = [('OL', 0, 'online'), ('OL CHRG', 50, 'online'),
                 ('OB', 0, 'battery-wait'), ('OB', 29, 'battery-wait'),
                 ('OB', 30, 'sustained-battery'), ('OB LB', 0, 'critical'),
                 ('FSD', 0, 'critical'), ('OFF', 0, 'critical'),
                 ('OL OB', 0, 'unknown'), ('OL ALARM', 0, 'unknown'),
                 ('INVALID', 0, 'unknown'), (None, 0, 'unknown')]
        for flags, elapsed, expected in cases:
            with self.subTest(flags=flags, elapsed=elapsed):
                self.assertEqual(decision(flags, elapsed), expected)

    def test_known_battery_deadline_survives_lost_or_invalid_status(self):
        self.assertEqual(advance('OB', None, 100), ('battery-wait', 100))
        self.assertEqual(advance(None, 100, 129), ('unknown', 100))
        self.assertEqual(advance(None, 100, 130), ('battery-status-lost', 100))
        self.assertEqual(advance('INVALID', 100, 130), ('battery-status-lost', 100))

    def test_communication_loss_alone_never_admits_shutdown(self):
        self.assertEqual(advance(None, None, 999), ('unknown', None))

    def test_confirmed_utility_return_clears_deadline(self):
        self.assertEqual(advance('OL', 100, 131), ('online', None))


if __name__ == '__main__':
    unittest.main()
