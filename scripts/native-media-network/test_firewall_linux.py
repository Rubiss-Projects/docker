"""Exercise real IPv4/IPv6 packets in two disposable namespaces, never the host."""

import json
import os
import selectors
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from firewall import render


def ready(process):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(10):
            raise RuntimeError("Isolated process did not become ready")
        return process.stdout.readline().strip()


@unittest.skipUnless(sys.platform == "linux" and getattr(os, "geteuid", lambda: -1)() == 0
                     and all(shutil.which(name) for name in ("unshare", "nsenter", "ip", "nft")),
                     "Requires Linux root and namespace/nftables tools")
class FirewallPackets(unittest.TestCase):
    def test_trusted_and_untrusted_dual_stack(self):
        processes = []
        try:
            pids = []
            for _ in range(2):
                process = subprocess.Popen(["unshare", "--net", sys.executable, "-u", "-c",
                    "import os,sys; print(os.getpid(),flush=True); sys.stdin.read()"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                processes.append(process)
                pids.append(int(ready(process)))

            def run(index, *args, **kwargs):
                return subprocess.run(["nsenter", "--target", str(pids[index]), "--net", *args],
                                      check=True, capture_output=True, text=True, timeout=15, **kwargs)

            run(0, "ip", "link", "add", "media-lan", "type", "veth", "peer", "name", "media-client")
            run(0, "ip", "link", "set", "media-client", "netns", str(pids[1]))
            for index, interface, suffix in [(0, "media-lan", "1"), (1, "media-client", "2")]:
                run(index, "ip", "link", "set", "lo", "up")
                run(index, "ip", "link", "set", interface, "up")
                for prefix in ("70", "71"):
                    run(index, "ip", "addr", "add", f"10.254.{prefix}.{suffix}/24", "dev", interface)
                    run(index, "ip", "-6", "addr", "add", f"fd00:{prefix}::{suffix}/64", "dev", interface, "nodad")
            with tempfile.TemporaryDirectory() as directory:
                rules = Path(directory) / "media.nft"
                rules.write_text(render("media-lan", ["10.254.70.0/24", "fd00:70::/64"], "br-test", "172.30.0.0/16"))
                # Both initial install and reload must keep the same admission policy.
                run(0, "nft", "-f", str(rules))
                run(0, "nft", "-f", str(rules))
            server_code = """
import socket,sys,threading
sockets=[]
def accept(s):
 while True:
  connection,_=s.accept();connection.close()
for port in (8089,32400):
 s=socket.socket(socket.AF_INET6);s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,0)
 s.bind(('::',port));s.listen();sockets.append(s)
 threading.Thread(target=accept,args=(s,),daemon=True).start()
print('READY',flush=True)
sys.stdin.read()
"""
            server = subprocess.Popen(["nsenter", "--target", str(pids[0]), "--net", sys.executable,
                                       "-u", "-c", server_code], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, text=True)
            processes.append(server)
            self.assertEqual(ready(server), "READY")
            client_code = """
import json,socket,sys
source,destination,port=sys.argv[1:]
s=socket.socket(socket.AF_INET6 if ':' in source else socket.AF_INET);s.settimeout(0.5)
s.bind((source,0))
try:s.connect((destination,int(port)));connected=True
except TimeoutError:connected=False
finally:s.close()
print(json.dumps(connected))
"""
            for source, destination, expected in [("10.254.70.2", "10.254.70.1", True),
                    ("10.254.71.2", "10.254.70.1", False), ("fd00:70::2", "fd00:70::1", True),
                    ("fd00:71::2", "fd00:70::1", False)]:
                for port in (8089, 32400):
                    with self.subTest(source=source, port=port):
                        result = run(1, sys.executable, "-c", client_code, source, destination, str(port))
                        self.assertEqual(json.loads(result.stdout), expected if port == 8089 else True)
        finally:
            # Closing stdin releases holders; namespaces and their veth links disappear.
            for process in reversed(processes):
                process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close()


if __name__ == "__main__":
    unittest.main()
