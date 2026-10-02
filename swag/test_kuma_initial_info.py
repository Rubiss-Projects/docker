import importlib.util
from pathlib import Path
import threading
import time
import unittest

spec = importlib.util.spec_from_file_location("patch", Path(__file__).parent / "init/kuma-initial-info/patch.py")
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class InitialInfoTests(unittest.TestCase):
    def api_class(self, emit_info):
        class Api:
            timeout = .1
            disconnected = False
            parent_info = None

            def __init__(self, url):
                self.worker = None
                if emit_info:
                    self.worker = threading.Thread(target=self.deliver)
                    self.worker.start()

            def deliver(self):
                time.sleep(.02)
                self._event_info({"version": "test"})

            def _event_info(self, data):
                self.parent_info = data

            def disconnect(self):
                Api.disconnected = True

        namespace = {"UptimeKumaApi": Api, "threading": threading}
        exec(patch.CLASS_SOURCE, namespace)
        return namespace["InitialInfoUptimeKumaApi"], Api

    def test_login_cannot_run_before_initial_info(self):
        cls, _ = self.api_class(True)
        api = cls("unused")
        api.worker.join()
        self.assertEqual(api.parent_info, {"version": "test"})
        self.assertTrue(api.initial_info_ready.is_set())

    def test_missing_info_disconnects_and_refuses_login(self):
        cls, base = self.api_class(False)
        with self.assertRaises(TimeoutError):
            cls("unused")
        self.assertTrue(base.disconnected)


if __name__ == "__main__":
    unittest.main()
