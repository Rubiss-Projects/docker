"""Regression coverage for maintenance scope, grace periods, and failure cleanup."""

import copy
import datetime as dt
import runpy
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
M = runpy.run_path(str(ROOT / "grafana-maintenance.py"))
NOW = dt.datetime(2026, 9, 13, 4, 0, tzinfo=dt.timezone.utc)


class FakeGrafana:
    def __init__(self):
        self.silences = {}
        self.expired = set()

    def request(self, method, path, body=None):
        if method == "POST":
            uid = body.get("id", str(uuid.uuid4()))
            self.silences[uid] = copy.deepcopy(body)
            return {"silenceID": uid}
        uid = path.rsplit("/", 1)[-1]
        if method == "GET":
            return copy.deepcopy(self.silences[uid])
        if method == "DELETE":
            self.expired.add(uid)


class MaintenanceTests(unittest.TestCase):
    def test_scope(self):
        for target in ["sunday-edge", "sunday-edge-dfs-6", "all", "docker-desktop", "/mnt/e/Docker/sunday-edge/"]:
            self.assertTrue(M["affected"]([target]))
        self.assertFalse(M["affected"](["plex", "grafana", "pi/cadvisor"]))

    def test_expiry_and_post_restart_grace(self):
        api = FakeGrafana()
        token = M["start"](api, 120, "deployment", NOW)
        availability, restart = token.split(":")
        self.assertEqual(api.silences[availability]["endsAt"], "2026-09-13T06:00:00Z")
        self.assertEqual(api.silences[restart]["endsAt"], "2026-09-13T06:35:00Z")
        M["stop"](api, token, NOW + dt.timedelta(minutes=10))
        self.assertEqual(api.expired, {availability})
        self.assertEqual(api.silences[restart]["endsAt"], "2026-09-13T04:45:00Z")
        for silence in api.silences.values():
            self.assertEqual(silence["matchers"][0]["value"], M["SERVICE"])
            self.assertFalse(silence["matchers"][1]["isRegex"])

    def test_overlap_is_independent(self):
        api = FakeGrafana()
        first = M["start"](api, 30, "first", NOW)
        second = M["start"](api, 30, "second", NOW)
        before = copy.deepcopy(api.silences[second.split(":")[1]])
        M["stop"](api, first, NOW)
        self.assertNotIn(second.split(":")[0], api.expired)
        self.assertEqual(api.silences[second.split(":")[1]], before)

    def test_refuse_unowned_silence(self):
        api = FakeGrafana()
        token = M["start"](api, 30, "test", NOW)
        api.silences[token.split(":")[1]]["createdBy"] = "someone else"
        with self.assertRaises(ValueError):
            M["stop"](api, token, NOW)
        self.assertFalse(api.expired)

    def test_partial_start_failure_removes_created_silence(self):
        api = FakeGrafana()
        request = api.request

        def fail_second_post(method, path, body=None):
            if method == "POST" and api.silences:
                raise OSError("Grafana disconnected")
            return request(method, path, body)

        api.request = fail_second_post
        with self.assertRaises(OSError):
            M["start"](api, 30, "test", NOW)
        self.assertEqual(api.expired, set(api.silences))

if __name__ == "__main__":
    unittest.main()
