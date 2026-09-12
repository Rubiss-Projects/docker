#!/usr/bin/env python3
"""Load the git-crypt registry secret into the deployment user's Docker login."""
import os
from pathlib import Path
import shlex
import subprocess
import sys


def main():
    secret = Path(__file__).resolve().parent.parent / "sunday-edge" / "registry.env.secret"
    if not secret.is_file() or secret.read_bytes().startswith(b"\x00GITCRYPT"):
        raise ValueError("Sunday Edge registry secret is missing or still encrypted; unlock git-crypt first")
    values = {}
    for line in secret.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition("=")
        if not separator or key not in {"GHCR_USERNAME", "GHCR_TOKEN"}:
            raise ValueError("Unexpected registry secret format")
        parts = shlex.split(raw)
        if len(parts) != 1:
            raise ValueError("Invalid registry secret value")
        values[key] = parts[0]
    if not values.get("GHCR_USERNAME") or not values.get("GHCR_TOKEN"):
        raise ValueError("Registry username and token are required")
    config = Path(os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker")))
    config.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The secret goes only to Docker's stdin, never the command, environment,
    # container configuration, or logs. Docker preserves other registry entries.
    result = subprocess.run(["docker", "--config", str(config), "login", "ghcr.io", "--username", values["GHCR_USERNAME"], "--password-stdin"],
                            input=values["GHCR_TOKEN"], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("GHCR login failed; check the encrypted read:packages credential")
    os.chmod(config / "config.json", 0o600)
    print("Sunday Edge private registry login configured.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not include captured registry output or credential values.
        print(str(error) if isinstance(error, (ValueError, RuntimeError)) else "Unable to configure the private registry login", file=sys.stderr)
        sys.exit(1)
