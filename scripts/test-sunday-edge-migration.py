#!/usr/bin/env python3
"""Rehearse the migration helpers and isolated replicas using disposable fixtures."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Locally built Sunday Edge compute image")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("migration", Path(__file__).with_name("migrate-sunday-edge-workers.py"))
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    image = args.image
    volume = "sunday-edge-migration-test-" + uuid.uuid4().hex
    containers = []
    migration.run(["docker", "volume", "create", "--label", "sunday-edge.fixture=true", volume], stdout=subprocess.DEVNULL)
    try:
        with tempfile.TemporaryDirectory(prefix="sunday-edge-fixture-") as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            (root / "state").mkdir()
            (root / "empty").mkdir()
            (root / "state" / "checkpoint.json").write_text('{"completed":17}')
            (root / "binary").write_bytes(bytes(range(256)))
            (root / "pointer").symlink_to("state/checkpoint.json")
            archive = Path(temporary) / "fixture.tar"
            migration.run(["tar", "-cpf", str(archive), "-C", str(root), "."])
            code = migration.output(["docker", "run", "--rm", "--network", "none", "--entrypoint", "cat", image, "/runtime/volume-data.py"])
            expected = json.loads(migration.run(["python3", "-c", code, "manifest", str(root)], capture_output=True, text=True).stdout)
            with archive.open("rb") as stream:
                migration.helper(image, volume, ["tar", "--no-same-owner", "-xpf", "-", "-C", "/data"], writable=True, stdin=stream)
            actual = json.loads(migration.helper(image, volume, ["python3", "/runtime/volume-data.py", "manifest", "/data"]))
            assert actual == expected, (actual, expected)
            migration.helper(image, volume, ["python3", "/runtime/volume-data.py", "finish-import", "/data"], writable=True)
            migration.helper(image, volume, ["python3", "/runtime/volume-data.py", "dfs-runtime", "/data"], writable=True)
            print(json.dumps({"fixtureImport": "verified", "manifest": actual}), flush=True)
            child = "import os,time,json;print(json.dumps({'id':os.environ['DFS_WORKER_ID'],'slot':os.environ['DFS_WORKER_SLOT'],'uid':os.getuid()}),flush=True);time.sleep(300)"
            for index in range(8):
                name = volume + "-" + str(index)
                containers.append(name)
                migration.run(["docker", "run", "-d", "--name", name, "--network", "none", "--read-only", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges:true", "--user", "10001:10001", "--memory", "64m", "--cpus", "0.1", "--pids-limit", "32",
                    "--mount", f"type=volume,source={volume},target=/data,volume-subpath=runtime,volume-nocopy", "-e", "DFS_WORKER_COUNT=8",
                    "-e", "DFS_WORKER_POOL_ID=fixture", image, "python3", "-u", "-c", child], stdout=subprocess.DEVNULL)
            for attempt in range(50):
                logs = [migration.output(["docker", "logs", name]) for name in containers]
                if all(logs):
                    break
                time.sleep(0.1)
            rows = [json.loads(log) for log in logs]
            assert sorted(int(row["slot"]) for row in rows) == list(range(1, 9))
            assert all(row["uid"] == 10001 for row in rows)
            print(json.dumps({"isolatedDockerReplicas": rows, "subpathMount": "verified"}), flush=True)
    finally:
        for name in containers:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        label = migration.output(["docker", "volume", "inspect", volume, "--format", '{{index .Labels "sunday-edge.fixture"}}'])
        assert volume.startswith("sunday-edge-migration-test-") and label == "true"
        migration.run(["docker", "volume", "rm", volume], stdout=subprocess.DEVNULL)
    print("Fixture resources removed; production sources and services were not changed.")


if __name__ == "__main__":
    main()
