#!/usr/bin/env python3
"""Reconcile the DFS pool. n8n invokes this through the Windows operation lock.

The runtime volume holds desired slots and cooldown state, not Compose overrides.
Only acknowledged, idle, excess logical slots can be stopped. Metrics/API failures
leave capacity unchanged; every Docker lifecycle mutation uses maintenance.
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / "sunday-edge"
CHECKPOINT = "sunday-edge-checkpoint-recovery"
MINIMUM, MAXIMUM = 2, 6
COOLDOWN_MS = 5 * 60_000
DEPLOY_LOCK = Path("/tmp/docker-compose-ops-deploy.lock.d")


def command(args, *, input=None, timeout=45):
    result = subprocess.run(args, cwd=STACK, input=input, text=True,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        # Config/inspect output can contain secrets: never forward it on failure.
        raise RuntimeError(f"{args[0]} operation failed with exit code {result.returncode}")
    return result.stdout.strip()


def control_read():
    return json.loads(command(["docker", "exec", CHECKPOINT, "node", "/runtime/pool-control.mjs", "read"]))


def control_write(state):
    command(["docker", "exec", "-i", CHECKPOINT, "node", "/runtime/pool-control.mjs", "write"],
            input=json.dumps(state))


def app_request(method, payload=None):
    environment = json.loads(command(["docker", "inspect", "--format", "{{json .Config.Env}}", CHECKPOINT]))
    env = dict(item.split("=", 1) for item in environment)
    origin = env["SUNDAY_EDGE_URL"].rstrip("/")
    if not origin.startswith("https://"):
        raise ValueError("The control plane must use HTTPS")
    body = json.dumps(payload, separators=(",", ":")) if payload is not None else ""
    timestamp = str(int(time.time() * 1000))
    pathname = "/api/compute/dfs/pool"
    signature = hmac.new(env["DFS_COMPUTE_SHARED_SECRET"].encode(),
                         f"{timestamp}.{method}.{pathname}.{hashlib.sha256(body.encode()).hexdigest()}".encode(),
                         hashlib.sha256).hexdigest()
    request = urllib.request.Request(origin + pathname, method=method,
        data=body.encode() if payload is not None else None,
        headers={"content-type": "application/json", "x-dfs-timestamp": timestamp, "x-dfs-signature": signature})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def snapshot():
    ids = command(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=sunday-edge",
                   "--filter", "label=com.docker.compose.service=dfs"]).split()
    if not ids or len(ids) > MAXIMUM:
        raise ValueError("Expected between one and six existing DFS containers")
    # Inspect only fields needed for identity, health, and private metrics access.
    template = '{{json .Id}} {{json .State.Status}} {{json .State.Health.Status}} {{json (index .NetworkSettings.Networks "proxynet").IPAddress}}'
    rows = [json.loads("[" + line.replace('" "', '","') + "]") for line in
            command(["docker", "inspect", "--format", template, *ids]).splitlines()]
    if any(status != "running" or health != "healthy" for _, status, health, _ in rows):
        raise ValueError("An existing DFS container is not healthy; holding capacity")
    script = """const fs=require('fs'); const rows=JSON.parse(fs.readFileSync(0,'utf8'));
Promise.all(rows.map(async ([id,ip])=>{const r=await fetch('http://'+ip+':9460/metrics',{signal:AbortSignal.timeout(5000)});
if(!r.ok) throw Error('metrics unavailable'); return {id,metrics:await r.text()};})).then(r=>console.log(JSON.stringify(r))).catch(()=>process.exit(1));"""
    measured = json.loads(command(["docker", "exec", "-i", CHECKPOINT, "node", "-e", script],
                                  input=json.dumps([[row[0], row[3]] for row in rows])))
    workers = []
    for row in measured:
        info = re.search(r'sunday_edge_dfs_worker_info\{[^\n]*slot="(\d+)"[^\n]*version="([^"]+)"', row["metrics"])
        idle = re.search(r'sunday_edge_dfs_worker_idle\{[^\n]+\} ([01])\n', row["metrics"])
        drained = re.search(r'sunday_edge_dfs_worker_drained\{[^\n]+\} ([01])\n', row["metrics"])
        if not info or not idle or not drained:
            raise ValueError("A DFS worker does not support autoscaling")
        workers.append({"id": row["id"], "slot": int(info[1]), "version": info[2],
                        "idle": idle[1] == "1", "drained": drained[1] == "1"})
    slots = [worker["slot"] for worker in workers]
    if len(set(slots)) != len(slots) or any(slot < 1 or slot > MAXIMUM for slot in slots):
        raise ValueError("Invalid or duplicated logical slots")
    return workers


def next_state(previous, demand, now):
    required = demand["desiredSlots"]
    if type(required) is not int or not MINIMUM <= required <= MAXIMUM:
        raise ValueError("Invalid desired slot count")
    state = dict(previous or {})
    current = state.get("desiredSlots", MINIMUM)
    low_since = state.get("lowSince")
    # A gap in successful samples invalidates the sustained quiet-period evidence.
    if now - state.get("updatedAt", 0) > 90_000:
        low_since = None
    if required >= current:
        current, low_since = required, None
    else:
        low_since = now if low_since is None else low_since
        if now - low_since >= COOLDOWN_MS:
            current, low_since = required, None
    state.update(protocolVersion=1, desiredSlots=current, maxSlots=MAXIMUM,
                 updatedAt=now, lowSince=low_since)
    # Wake the baseline as well as new replicas whenever runnable work exists.
    if demand["pending"] > 0 or "wakeToken" not in state:
        state["wakeToken"] = str(uuid.uuid4())
    return state


def report(state, workers):
    # Identity comes from the deployed Compose pool, never from workflow input.
    config = json.loads(command(["docker", "compose", "config", "--format", "json"]))
    pool_id = config["services"]["dfs"]["environment"]["DFS_WORKER_POOL_ID"]
    app_request("POST", {"poolId": pool_id, "desiredSlots": state["desiredSlots"],
                        "maxSlots": MAXIMUM, "onlineSlots": [worker["slot"] for worker in workers]})


def lifecycle(args):
    command([sys.executable, str(ROOT / "scripts/grafana-maintenance.py"), "run",
             "--ttl-minutes", "10", "--reason", "DFS autoscaling", "--", *args], timeout=240)


def reconcile(dry_run=False):
    workers = snapshot()
    demand = app_request("GET")
    if demand.get("protocolVersion") != 1 or any(worker["version"] != demand.get("workerVersion") for worker in workers):
        raise ValueError("Worker/control-plane versions do not match")
    sampled = dt.datetime.fromisoformat(demand["sampledAt"].replace("Z", "+00:00")).timestamp()
    if abs(time.time() - sampled) > 60:
        raise ValueError("Demand sample is stale")
    previous = control_read()
    if previous is None:
        # Losing the state file is not evidence of five quiet minutes.
        previous = {"desiredSlots": max(MINIMUM, max(worker["slot"] for worker in workers))}
    state = next_state(previous, demand, int(time.time() * 1000))
    desired = state["desiredSlots"]
    excess = [worker for worker in workers if worker["slot"] > desired]
    removable = [worker for worker in excess if worker["idle"] and worker["drained"]]
    result = {"desiredSlots": desired, "onlineSlots": sorted(worker["slot"] for worker in workers),
              "demand": demand, "drainingSlots": sorted(worker["slot"] for worker in excess), "dryRun": dry_run}
    if dry_run:
        return result
    control_write(state)
    # Remove only explicit logical identities; Compose's replica ordinals need
    # not match the OS-locked slots, so a blind scale-down can kill the wrong job.
    if removable:
        ids = [worker["id"] for worker in removable]
        # Acknowledged drains have no outstanding lease/poll/completion request.
        # Atomic removal avoids a crash leaving stopped replicas that Compose
        # could unexpectedly revive in the next reconciliation.
        lifecycle(["docker", "rm", "--force", *ids])
        workers = [worker for worker in workers if worker not in removable]
    if len(workers) < desired:
        lifecycle(["docker", "compose", "up", "-d", "--no-deps", "--no-recreate", "--pull", "never",
                   "--scale", f"dfs={desired}", "--wait", "--wait-timeout", "90", "dfs"])
        workers = snapshot()
    report(state, workers)
    return result


def reset_control():
    # Called after Compose reapplies the baseline, under deployment/nightly locks.
    deadline = time.monotonic() + 90
    while True:
        try:
            workers = snapshot()
            break
        except (RuntimeError, ValueError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)
    if len(workers) != MINIMUM or {worker["slot"] for worker in workers} != {1, 2}:
        raise ValueError("Compose must restore the two baseline logical slots before reset")
    state = {"protocolVersion": 1, "desiredSlots": MINIMUM, "maxSlots": MAXIMUM,
             "wakeToken": str(uuid.uuid4()), "updatedAt": int(time.time() * 1000), "lowSince": None}
    control_write(state)
    report(state, workers)
    return {"reset": True, "desiredSlots": MINIMUM}


@contextlib.contextmanager
def deployment_lock():
    DEPLOY_LOCK.mkdir(exist_ok=True)
    descriptor = os.open(DEPLOY_LOCK, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset-control", action="store_true")
    args = parser.parse_args()
    if args.reset_control:
        print(json.dumps(reset_control()))
        return
    if (STACK / "autoscaling.paused").exists():
        print(json.dumps({"paused": True}))
        return
    try:
        with deployment_lock():
            print(json.dumps(reconcile(args.dry_run)))
    except BlockingIOError:
        print(json.dumps({"skipped": "deployment or another controller owns the lock"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "message": "Autoscaling failed; inspect host/controller health. No capacity is inferred from missing data."}), file=sys.stderr)
        raise SystemExit(1)
