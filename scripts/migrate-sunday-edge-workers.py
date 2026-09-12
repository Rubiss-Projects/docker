#!/usr/bin/env python3
"""Stop legacy workers, preserve originals, and verify imports into Docker volumes.

Run on ben-server after image and Compose validation. This does NOT start the
containers: review the verified manifest, then start the Sunday Edge stack.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SOURCES = {
    "sunday-edge-dfs-data": "/var/lib/sunday-edge-dfs-simulator",
    "sunday-edge-analytics-data": "/var/lib/fantasy-analytics",
    "sunday-edge-maintenance-data": "/var/lib/sunday-edge-maintenance",
    "sunday-edge-research-data": "/var/lib/sunday-edge-research",
}
TIMERS = ["sunday-edge-analytics.timer", "sunday-edge-monitor-watchdog.timer", "sunday-edge-research-sources.timer"]
SERVICES = [f"sunday-edge-dfs-simulator@{slot}.service" for slot in range(1, 7)] + [
    "sunday-edge-analytics.service", "sunday-edge-maintenance.service", "sunday-edge-dfs-checkpoint-recovery.service",
    "sunday-edge-monitor-watchdog.service", "sunday-edge-research-sources.service"]


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def output(args):
    return run(args, capture_output=True, text=True).stdout.strip()


def helper(image, volume, command, *, writable=False, stdin=None):
    options = ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0", "--cap-drop", "ALL",
        "--cap-add", "DAC_OVERRIDE", "--security-opt", "no-new-privileges:true", "--memory", "256m", "--cpus", "1", "--pids-limit", "64"]
    if writable:
        options += ["--cap-add", "CHOWN", "--cap-add", "FOWNER"]
    if stdin is not None:
        options += ["-i"]
    options += ["--mount", f"type=volume,source={volume},target=/data,volume-nocopy" + ("" if writable else ",readonly"), "--entrypoint", command[0], image, *command[1:]]
    return run(options, stdin=stdin, capture_output=True, text=stdin is None).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Previously validated Sunday Edge compute image (prefer a digest)")
    parser.add_argument("--execute", action="store_true", help="Stop legacy services, back up data, and import private volumes")
    args = parser.parse_args()
    if os.geteuid() != 0 or sys.platform != "linux":
        raise ValueError("Run as root in ben-server Ubuntu after the Windows E: storage preflight")
    for source in SOURCES.values():
        if Path(source).resolve() != Path(source) or not Path(source).is_dir():
            raise ValueError(f"Unexpected source directory: {source}")
    source_label = output(["docker", "image", "inspect", args.image, "--format", '{{index .Config.Labels "org.opencontainers.image.source"}}'])
    if source_label != "https://github.com/Rubiss/fantasy-football":
        raise ValueError("The helper image must come from Sunday Edge")
    existing = set(output(["docker", "volume", "ls", "--format", "{{.Name}}"]).splitlines())
    if existing.intersection(SOURCES):
        raise ValueError("A destination volume already exists. Inspect it; never overwrite or delete it to rerun migration.")
    states = {unit: dict(line.split("=", 1) for line in output(["systemctl", "show", unit, "-p", "ActiveState", "-p", "UnitFileState"]).splitlines()) for unit in TIMERS + SERVICES}
    print(json.dumps({"sourceDirectories": SOURCES, "legacyUnitStates": states, "execute": args.execute}), flush=True)
    if not args.execute:
        return
    os.umask(0o077)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = Path("/var/backups/sunday-edge-containers") / stamp
    backup.mkdir(parents=True, mode=0o700)
    manifest = {"createdAt": stamp, "legacyUnitStates": states, "volumes": {}, "helperImage": args.image}
    manifest_path = backup / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Backup directory: {backup}", flush=True)
    # Stop recurring triggers first; no old and new worker may share a live role.
    run(["systemctl", "disable", "--now", *TIMERS])
    run(["systemctl", "stop", *SERVICES])
    for unit in SERVICES:
        if states[unit]["UnitFileState"] == "enabled":
            run(["systemctl", "disable", unit])
    for unit in TIMERS + SERVICES:
        state = output(["systemctl", "show", unit, "-p", "ActiveState", "--value"])
        if state not in ("inactive", "failed"):
            raise RuntimeError(f"Legacy unit did not stop: {unit}")
    # Save the environment files in a private archive as well as preserving /etc.
    run(["tar", "-cpf", str(backup / "environments.tar"), "-C", "/etc",
         "sunday-edge-analytics.env", "sunday-edge-dfs-simulator.env", "sunday-edge-maintenance.env", "sunday-edge-monitor-watchdog.env"])
    for volume, source in SOURCES.items():
        print(f"Snapshot and import: {volume}", flush=True)
        archive = backup / f"{volume}.tar"
        run(["tar", "--acls", "--xattrs", "-cpf", str(archive), "-C", source, "."])
        # Run the exact same manifest implementation on source and destination.
        manifest_code = output(["docker", "run", "--rm", "--network", "none", "--entrypoint", "cat", args.image, "/runtime/volume-data.py"])
        source_result = json.loads(run([sys.executable, "-c", manifest_code, "manifest", source], capture_output=True, text=True).stdout)
        run(["docker", "volume", "create", "--label", "sunday-edge.migration=" + stamp, volume], stdout=subprocess.DEVNULL)
        with archive.open("rb") as stream:
            helper(args.image, volume, ["tar", "--no-same-owner", "-xpf", "-", "-C", "/data"], writable=True, stdin=stream)
        copied = json.loads(helper(args.image, volume, ["python3", "/runtime/volume-data.py", "manifest", "/data"]))
        if copied != source_result:
            raise RuntimeError(f"Checksum mismatch for {volume}; legacy services remain stopped and originals remain intact")
        helper(args.image, volume, ["python3", "/runtime/volume-data.py", "finish-import", "/data"], writable=True)
        if volume == "sunday-edge-dfs-data":
            helper(args.image, volume, ["python3", "/runtime/volume-data.py", "dfs-runtime", "/data"], writable=True)
        if volume == "sunday-edge-analytics-data":
            helper(args.image, volume, ["python3", "/runtime/volume-data.py", "clear-analytics-lock", "/data"], writable=True)
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        manifest["volumes"][volume] = {"source": source, "content": copied, "archiveSha256": digest.hexdigest(), "verified": True}
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(json.dumps({"volume": volume, **copied, "verified": True}), flush=True)
    print(f"Imports verified. Originals retained. Start Compose, then verify workloads and monitoring. Manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
