import copy
import unittest

from firewall import render
from prepare import prepare


class NetworkTests(unittest.TestCase):
    def media(self, name):
        return {"name": "existing-project", "services": {name: {
            "container_name": name, "image": "vendor/media@sha256:unchanged",
            "networks": {"proxynet": None}, "ports": [{"target": 8089}],
            "volumes": [{"type": "volume", "source": "original", "target": "/config"}],
            "environment": {"SECRET": "retained"}, "cpuset": "0-7",
            "deploy": {"resources": {"reservations": {"devices": [{"driver": "nvidia"}]}}},
        }}, "volumes": {"original": {"external": True}}}

    def test_media_keeps_identity_storage_gpu_and_secrets(self):
        for name in ("plex", "channels-dvr"):
            with self.subTest(name=name):
                source = self.media(name)
                before = copy.deepcopy(source)
                result = prepare(source, name)
                self.assertEqual(source, before)
                service = result["services"][name]
                self.assertEqual(service["network_mode"], "host")
                self.assertNotIn("ports", service)
                self.assertNotIn("networks", service)
                for key in source["services"][name].keys() - {"ports", "networks"}:
                    self.assertEqual(service[key], source["services"][name][key])
                self.assertEqual(result["volumes"], source["volumes"])
                self.assertEqual(prepare(result, name), result)

    def test_tracearr_dependencies_and_unrelated_aliases_untouched(self):
        source = self.media("tracearr")
        source["services"]["tracearr"]["extra_hosts"] = ["other=192.0.2.1"]
        source["services"]["database"] = {"image": "postgres", "volumes": ["db:/var/lib/postgresql"]}
        result = prepare(source, "tracearr")
        self.assertEqual(result["services"]["database"], source["services"]["database"])
        service = result["services"]["tracearr"]
        self.assertEqual(service["networks"], {"proxynet": None})
        self.assertEqual(service["extra_hosts"], {"other": "192.0.2.1", "plex": "host-gateway", "channels-dvr": "host-gateway"})

    def test_refuses_windows_storage_and_conflicting_aliases(self):
        for source_path in ("/usr/lib/wsl/lib", "/mnt/e/Docker/plex/config", "./config", "C:/config"):
            source = self.media("plex")
            source["services"]["plex"]["volumes"] = [{"type": "bind", "source": source_path}]
            with self.assertRaises(ValueError):
                prepare(source, "plex")
        source = self.media("homepage")
        source["services"]["homepage"]["extra_hosts"] = {"plex": "192.0.2.2"}
        with self.assertRaises(ValueError):
            prepare(source, "homepage")

    def test_firewall_is_dual_stack_scoped_and_keeps_plex_public_port(self):
        rules = render("eno1", ["192.168.50.0/24", "fd00::/64", "fe80::/64"], "br-example", "172.30.0.0/16")
        self.assertIn("table inet native_media", rules)
        self.assertNotIn("flush ruleset", rules)
        self.assertNotIn("32400", rules)
        self.assertNotIn("ct state established", rules)
        self.assertIn('iifname "eno1" ip6 saddr fd00::/64 accept', rules)
        self.assertIn("8089", rules)
        for arguments in [("bad\"iface", ["192.168.1.0/24"], "br0", "172.30.0.0/16"), ("eno1", ["0.0.0.0/0"], "br0", "172.30.0.0/16")]:
            with self.assertRaises(ValueError):
                render(*arguments)


if __name__ == "__main__":
    unittest.main()
