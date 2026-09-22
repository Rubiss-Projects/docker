import importlib.util
import json
import fcntl
from pathlib import Path
import signal
import sys
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("rpc-health.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def server(self, mode="healthy"):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append(request)
                if self.headers.get("X-Transmission-Session-Id") != "token" or mode == "challenge_loop":
                    self.send_response(409)
                    self.send_header("X-Transmission-Session-Id", "token")
                    self.end_headers()
                    return
                if mode == "timeout":
                    time.sleep(0.2)
                    return
                if mode == "trickle":
                    self.send_response(200)
                    self.end_headers()
                    try:
                        for _ in range(100):
                            self.wfile.write(b" ")
                            self.wfile.flush()
                            time.sleep(0.02)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                args = {"torrentCount": 1408, "activeTorrentCount": 1408, "pausedTorrentCount": 0,
                        "downloadSpeed": 50000000, "uploadSpeed": 30000000}
                if request["method"] == "torrent-get":
                    args = {"torrents": [{"status": 6, "error": 0, "peersConnected": 2},
                                         {"status": 4, "error": 1, "peersConnected": 3}]}
                if mode == "missing_fields":
                    args = {}
                body = json.dumps({"result": "failure" if mode == "rpc_error" else "success", "arguments": args}).encode()
                if mode == "bad_json":
                    body = b"not-json"
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return probe.RPC(f"http://127.0.0.1:{server.server_port}/transmission/rpc", timeout=0.05), calls

    def test_successful_handshake_and_aggregate_only_inventory(self):
        rpc, calls = self.server()
        result = probe.collect(rpc, inventory=True)
        self.assertEqual(result["rpc_up"], 1)
        self.assertEqual(result["inventory_up"], 1)
        self.assertEqual(result["peers"], 5)
        self.assertEqual(result["torrent_errors"], 1)
        self.assertEqual(result["download_bytes_per_second"], 50000000)
        self.assertEqual(calls[-1]["arguments"]["fields"], ["status", "error", "peersConnected"])
        self.assertTrue(all(c["method"] in ("session-stats", "torrent-get") for c in calls))

    def test_listener_is_not_functional_health(self):
        for mode in ("challenge_loop", "timeout", "missing_fields", "bad_json", "rpc_error"):
            with self.subTest(mode=mode):
                rpc, calls = self.server(mode)
                result = probe.collect(rpc)
                self.assertEqual(result["listener_up"], 1)
                self.assertEqual(result["rpc_up"], 0)
                self.assertNotIn("download_bytes_per_second", result)
                self.assertLessEqual(len(calls), 2)

    def test_session_renegotiates(self):
        rpc, calls = self.server()
        rpc.session = "expired"
        self.assertEqual(probe.collect(rpc)["rpc_up"], 1)
        self.assertEqual(len(calls), 2)

    def test_absolute_deadline_bounds_trickling_response(self):
        rpc, _ = self.server("trickle")
        def deadline(_signum, _frame):
            raise probe.ProbeError("deadline_exceeded")
        old = signal.signal(signal.SIGALRM, deadline)
        started = time.monotonic()
        try:
            signal.setitimer(signal.ITIMER_REAL, 0.2)
            result = probe.collect(rpc)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
        self.assertEqual(result["rpc_up"], 0)
        self.assertEqual(result["error"], "deadline_exceeded")
        self.assertLess(time.monotonic() - started, 1)

    def test_overlapping_metrics_probe_is_not_started(self):
        with open('/tmp/transmission-metrics.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(sys, 'argv', ['probe', '--metrics']), patch.object(probe, 'collect') as collect:
                self.assertEqual(probe.main(), 1)
                collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
