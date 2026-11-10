import copy
import importlib.util
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch as mock_patch

ROOT = Path(__file__).parent / "init/kuma-initial-info"
spec = importlib.util.spec_from_file_location("kuma_sync", ROOT / "sync.py")
sync = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sync
spec.loader.exec_module(sync)


def container(container_name="plex", **fields):
    return SimpleNamespace(name=container_name, labels={sync.PREFIX + key: value for key, value in fields.items()})


def monitor(monitor_id=141, name="Plex", tag="plex", kind="http", **fields):
    return {"id": monitor_id, "name": name, "type": kind,
            "tags": [{"name": "swag", "value": tag}] if tag else [],
            "url": "http://old/", "parent": None, "active": False,
            "notificationIDList": [7], **fields}


class Api:
    """No delete/pause/resume API: reconciliation must not need them."""
    def __init__(self, monitors):
        self.monitors = copy.deepcopy(monitors)
        self.writes = []
        self.history = {m["id"]: ["original heartbeat"] for m in monitors}

    def get_monitors(self):
        result = copy.deepcopy(self.monitors)
        for item in result:
            item.update(active=False, forceInactive=True)
        return result

    def get_monitor(self, monitor_id):
        return copy.deepcopy(next(m for m in self.monitors if m["id"] == monitor_id))

    def get_tags(self):
        return [{"id": 9, "name": "swag"}]

    def get_notifications(self):
        return [{"id": 1, "isDefault": True}, {"id": 2, "isDefault": False}]

    def edit_monitor(self, monitor_id, **fields):
        self.writes.append(("edit", monitor_id, fields))
        next(m for m in self.monitors if m["id"] == monitor_id).update(fields)
        return {"monitorID": monitor_id}

    def add_monitor(self, **fields):
        monitor_id = max((m["id"] for m in self.monitors), default=0) + 1
        self.monitors.append({"id": monitor_id, "tags": [], **fields})
        self.writes.append(("add", monitor_id, fields))
        return {"monitorID": monitor_id}

    def add_monitor_tag(self, tag_id, monitor_id, value):
        next(m for m in self.monitors if m["id"] == monitor_id)["tags"].append({"name": "swag", "value": value})
        self.writes.append(("tag", monitor_id, value))


class HistorySyncTests(unittest.TestCase):
    def test_url_edit_preserves_identity_history_pause_and_notifications(self):
        for active in (False, True):
            with self.subTest(active=active):
                api = Api([monitor(active=active)])
                plan = sync.build_plan(api, [container(url="http://new/")], "example.test")
                sync.apply_plan(api, plan)
                self.assertEqual(api.writes, [("edit", 141, {"url": "http://new/"})])
                self.assertEqual(api.get_monitor(141)["active"], active)
                self.assertEqual(api.get_monitor(141)["notificationIDList"], [7])
                self.assertEqual(api.history, {141: ["original heartbeat"]})

    def test_absent_monitors_and_empty_groups_are_retained(self):
        api = Api([monitor(), monitor(66, "Media", "media", "group")])
        before = copy.deepcopy(api.monitors)
        plan = sync.build_plan(api, [], "example.test")
        sync.apply_plan(api, plan)
        self.assertEqual(plan.retained, 1)
        self.assertEqual(api.monitors, before)
        self.assertFalse(api.writes)

    def test_new_monitors_use_defaults_then_repeated_sync_is_noop(self):
        api = Api([])
        containers = [container(parent="Media", accepted_statuscodes="200-299, 401")]
        plan = sync.build_plan(api, containers, "example.test")
        self.assertFalse(api.writes)  # Planning/dry-run does not create a group or tag.
        sync.apply_plan(api, plan)
        created = next(m for m in api.monitors if m["type"] == "http")
        self.assertEqual(created["notificationIDList"], [1])
        self.assertEqual(created["parent"], 1)
        self.assertEqual(created["accepted_statuscodes"], ["200-299", "401"])
        api.writes.clear()
        sync.apply_plan(api, sync.build_plan(api, containers, "example.test"))
        self.assertFalse(api.writes)

    def test_ambiguous_identity_or_unlinked_name_aborts_before_writes(self):
        for monitors in ([monitor(), monitor(142)], [monitor(tag=None)],
                         [monitor(66, "Media", "a", "group"), monitor(67, "Media", "b", "group")]):
            api = Api(monitors)
            with self.assertRaises(ValueError):
                sync.build_plan(api, [container(parent="Media")], "example.test")
            self.assertFalse(api.writes)

    def test_pause_or_identity_labels_are_rejected(self):
        for key in ("active", "id", "forceInactive", "tags"):
            api = Api([monitor()])
            with self.assertRaises(ValueError):
                sync.build_plan(api, [container(**{key: "1"})], "example.test")
            self.assertFalse(api.writes)

    def test_explicit_notification_choices_do_not_union_defaults(self):
        api = Api([monitor()])
        sync.apply_plan(api, sync.build_plan(api, [container(notificationIDList="8, 8, 9")], "example.test"))
        self.assertEqual(api.get_monitor(141)["notificationIDList"], [8, 9])

    def test_group_type_and_duplicate_requested_names_abort(self):
        for containers in ([container(type="group")], [container("a", name="Same"), container("b", name="Same")]):
            api = Api([monitor()])
            with self.assertRaises(ValueError):
                sync.build_plan(api, containers, "example.test")
            self.assertFalse(api.writes)

    def test_patch_rejects_unknown_sources_without_touching_either_file(self):
        spec = importlib.util.spec_from_file_location("kuma_patch", ROOT / "patch.py")
        patch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(patch)
        with tempfile.TemporaryDirectory() as folder:
            service = Path(folder) / "service.py"
            entry = Path(folder) / "entry.py"
            service.write_bytes(b"unknown service")
            entry.write_bytes(b"unknown entry")
            with self.assertRaises(RuntimeError):
                patch.patch(service, entry)
            self.assertEqual(service.read_bytes(), b"unknown service")
            self.assertEqual(entry.read_bytes(), b"unknown entry")

    def test_patch_installs_idempotently_and_validates_entry_before_service_write(self):
        spec = importlib.util.spec_from_file_location("kuma_patch", ROOT / "patch.py")
        patch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(patch)
        original = b'import requests\nclass UptimeKumaService:\n    def connect(self, url):\n        self.api = UptimeKumaApi(url)\n'
        expected = original.decode().replace("import requests\n", "import requests\nimport threading\n").replace(
            "class UptimeKumaService:", patch.CLASS_SOURCE + "\n\n\nclass UptimeKumaService:").replace(
            "self.api = UptimeKumaApi(url)", "self.api = InitialInfoUptimeKumaApi(url)").encode()
        upstream = b"# reviewed upstream entrypoint\n"
        with tempfile.TemporaryDirectory() as folder, mock_patch.multiple(
                patch, ORIGINAL=hashlib.sha256(original).hexdigest(), PATCHED=hashlib.sha256(expected).hexdigest(),
                UPSTREAM_ENTRYPOINT=hashlib.sha256(upstream).hexdigest()):
            service = Path(folder) / "service.py"
            entry = Path(folder) / "entry.py"
            service.write_bytes(original)
            entry.write_bytes(b"unknown entry")
            with self.assertRaises(RuntimeError):
                patch.patch(service, entry)
            self.assertEqual(service.read_bytes(), original)
            entry.write_bytes(upstream)
            patch.patch(service, entry)
            self.assertEqual(service.read_bytes(), expected)
            self.assertEqual(entry.read_bytes(), (ROOT / "sync.py").read_bytes())
            before = (service.stat().st_mtime_ns, entry.stat().st_mtime_ns)
            patch.patch(service, entry)
            self.assertEqual(before, (service.stat().st_mtime_ns, entry.stat().st_mtime_ns))


if __name__ == "__main__":
    unittest.main()
