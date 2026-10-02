"""Retain the tested initial-info barrier across SWAG container recreation."""

import hashlib
from pathlib import Path

ORIGINAL = "b8e70d275ea0161f4b7e8d4b15dc9135e5e1d65d216c7665368023a259eed224"
PATCHED = "c163c809fb0a503b7c21c79cb3c5cbab00d39824f858a5e8bd1c9dc8044e8d3b"
TARGET = Path("/app/auto_uptime_kuma/uptime_kuma_service.py")
CLASS_SOURCE = '''class InitialInfoUptimeKumaApi(UptimeKumaApi):
    def __init__(self, url, **kwargs):
        self.initial_info_ready = threading.Event()
        super().__init__(url, **kwargs)
        if not self.initial_info_ready.wait(self.timeout):
            self.disconnect()
            raise TimeoutError("Initial Kuma info event did not arrive")

    def _event_info(self, data):
        super()._event_info(data)
        self.initial_info_ready.set()'''


def patch(target=TARGET):
    original = target.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest == PATCHED:
        print("[kuma-initial-info] Reviewed login barrier already present")
        return
    if digest != ORIGINAL:
        raise RuntimeError("Kuma mod source changed; review before applying the login barrier")
    text = original.decode("utf-8")
    text = text.replace("import requests\n", "import requests\nimport threading\n", 1)
    text = text.replace("class UptimeKumaService:", CLASS_SOURCE + "\n\n\nclass UptimeKumaService:", 1)
    text = text.replace("self.api = UptimeKumaApi(url)", "self.api = InitialInfoUptimeKumaApi(url)", 1)
    result = text.encode("utf-8")
    if hashlib.sha256(result).hexdigest() != PATCHED:
        raise RuntimeError("Kuma login patch differs from the tested recovery source")
    target.write_bytes(result)
    print("[kuma-initial-info] Installed reviewed initial-info login barrier")


if __name__ == "__main__":
    patch()
