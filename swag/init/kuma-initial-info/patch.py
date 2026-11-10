"""Install reviewed login and history-preserving sync across SWAG recreation."""

import hashlib
import os
from pathlib import Path
import tempfile

ORIGINAL = "b8e70d275ea0161f4b7e8d4b15dc9135e5e1d65d216c7665368023a259eed224"
PATCHED = "c163c809fb0a503b7c21c79cb3c5cbab00d39824f858a5e8bd1c9dc8044e8d3b"
TARGET = Path("/app/auto_uptime_kuma/uptime_kuma_service.py")
ENTRYPOINT = Path("/app/auto-uptime-kuma.py")
UPSTREAM_ENTRYPOINT = "5ddce335938d176270dd08d1160fa25509219ac56cc538e3017197e752d88a4c"
SYNC = Path(__file__).with_name("sync.py")
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


def service_patch(target):
    original = target.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest == PATCHED:
        return original
    if digest != ORIGINAL:
        raise RuntimeError("Kuma mod source changed; review before applying the login barrier")
    text = original.decode("utf-8")
    text = text.replace("import requests\n", "import requests\nimport threading\n", 1)
    text = text.replace("class UptimeKumaService:", CLASS_SOURCE + "\n\n\nclass UptimeKumaService:", 1)
    text = text.replace("self.api = UptimeKumaApi(url)", "self.api = InitialInfoUptimeKumaApi(url)", 1)
    result = text.encode("utf-8")
    if hashlib.sha256(result).hexdigest() != PATCHED:
        raise RuntimeError("Kuma login patch differs from the tested recovery source")
    return result


def replace_reviewed(path, content):
    if path.read_bytes() == content:
        return
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".reviewed-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        temporary.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def patch(target=TARGET, entrypoint=ENTRYPOINT, sync=SYNC):
    # Validate both installed sources before changing either. Unknown mod releases
    # need review; never fall back to the upstream delete-and-recreate behavior.
    service = service_patch(target)
    helper = sync.read_bytes()
    entry = entrypoint.read_bytes()
    if hashlib.sha256(entry).hexdigest() != UPSTREAM_ENTRYPOINT and entry != helper:
        raise RuntimeError("Kuma entrypoint changed; review before installing history protection")
    compile(helper, str(sync), "exec")
    replace_reviewed(target, service)
    replace_reviewed(entrypoint, helper)
    print("[kuma-initial-info] Reviewed login barrier and history-preserving sync installed")


if __name__ == "__main__":
    patch()
