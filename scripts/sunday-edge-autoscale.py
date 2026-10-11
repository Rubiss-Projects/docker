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
import math
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
MINIMUM, MAXIMUM = 2, 8
COOLDOWN_MS = 5 * 60_000
RESOURCE_MAX_AGE_MS = 60_000
CPU_LIMIT_PERCENT = 85
MEMORY_RESERVE_BYTES = 2 * 1024 ** 3
MAX_ADDITIONS = 2
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
    # Legacy controllers keep the six-slot policy until they explicitly opt in.
    url = origin + pathname + ("?maxSlots=8" if method == "GET" else "")
    request = urllib.request.Request(url, method=method,
        data=body.encode() if payload is not None else None,
        headers={"content-type": "application/json", "x-dfs-timestamp": timestamp, "x-dfs-signature": signature})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def snapshot():
    ids = command(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=sunday-edge",
                   "--filter", "label=com.docker.compose.service=dfs"]).split()
    if not ids or len(ids) > MAXIMUM:
        raise ValueError("Expected between one and eight existing DFS containers")
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


def linux_resources():
    """Measure this WSL VM, including other containers and Linux services."""
    def cpu_times():
        # Guest ticks are already included in user/nice ticks.
        ticks = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
        return sum(ticks), ticks[3] + ticks[4]

    before_total, before_idle = cpu_times()
    time.sleep(1)
    after_total, after_idle = cpu_times()
    if after_total <= before_total or after_idle < before_idle:
        raise ValueError("Invalid Linux CPU sample")
    memory = dict(re.findall(r"^(\w+):\s+(\d+) kB$", Path("/proc/meminfo").read_text(), re.MULTILINE))
    return {"sampledAt": int(time.time() * 1000), "cpuCount": os.cpu_count(),
            "cpuPercent": 100 * (1 - (after_idle - before_idle) / (after_total - before_total)),
            "availableMemoryBytes": int(memory["MemAvailable"]) * 1024}


def resource_budget(windows, linux, cpu_per_worker, memory_per_worker, now):
    """Admit full replica limits while retaining headroom on BOTH host systems."""
    if not math.isfinite(cpu_per_worker) or cpu_per_worker <= 0 or memory_per_worker <= 0:
        raise ValueError("Invalid worker resource limits")
    allowed = MAX_ADDITIONS
    for resources in (windows, linux):
        if not isinstance(resources, dict):
            raise ValueError("Missing resource sample")
        sampled = resources["sampledAt"]
        cores = resources["cpuCount"]
        cpu = resources["cpuPercent"]
        memory = resources["availableMemoryBytes"]
        if (type(sampled) is not int or abs(now - sampled) > RESOURCE_MAX_AGE_MS
                or type(cores) is not int or cores < 1
                or type(cpu) not in (int, float) or not math.isfinite(cpu) or not 0 <= cpu <= 100
                or type(memory) is not int or memory < 0):
            raise ValueError("Invalid or stale resource sample")
        cpu_slots = math.floor(cores * max(0, CPU_LIMIT_PERCENT - cpu) / 100 / cpu_per_worker)
        memory_slots = max(0, (memory - MEMORY_RESERVE_BYTES) // memory_per_worker)
        allowed = min(allowed, cpu_slots, memory_slots)
    return allowed


def admission(windows):
    try:
        # Budget the desired Compose limits, not potentially older running quotas.
        config = json.loads(command(["docker", "compose", "config", "--format", "json"]))
        limits = config["services"]["dfs"]
        linux = linux_resources()
        allowed = resource_budget(windows, linux, float(limits["cpus"]), int(limits["mem_limit"]),
                                  int(time.time() * 1000))
        return {"additionalSlots": allowed, "reason": "HEADROOM" if allowed else "RESOURCE_PRESSURE",
                "validUntil": min(windows["sampledAt"], linux["sampledAt"]) + RESOURCE_MAX_AGE_MS,
                "windows": windows, "linux": linux}
    except (KeyError, ValueError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired):
        # Telemetry failures hold additions without interrupting leases or drains.
        return {"additionalSlots": 0, "reason": "RESOURCE_SAMPLE_UNAVAILABLE"}


def next_state(previous, demand, now):
    required = demand["desiredSlots"]
    if type(required) is not int or not MINIMUM <= required <= MAXIMUM:
        raise ValueError("Invalid desired slot count")
    state = dict(previous or {})
    current = state.get("desiredSlots", MINIMUM)
    low_since = state.get("lowSince")
    low_desired = state.get("lowDesired")
    # A gap in successful samples invalidates the sustained quiet-period evidence.
    if now - state.get("updatedAt", 0) > 90_000:
        low_since = None
    if required >= current:
        current, low_since, low_desired = required, None, None
    else:
        # A different recommendation must establish its own quiet period.
        if low_since is None or required != low_desired:
            low_since = now
        low_desired = required
        if now - low_since >= COOLDOWN_MS:
            current, low_since, low_desired = required, None, None
    state.update(protocolVersion=1, desiredSlots=current, maxSlots=MAXIMUM,
                 updatedAt=now, lowSince=low_since, lowDesired=low_desired)
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


def lifecycle(args, admission_valid_until=None):
    if admission_valid_until is not None:
        # This guard executes AFTER Grafana/Kuma setup, immediately before Docker.
        # Maintenance setup can exceed the lifetime of otherwise fresh samples.
        guard = ("import subprocess, sys, time\n"
                 "if time.time() * 1000 > int(sys.argv[1]):\n"
                 "    print('Resource admission expired during maintenance; holding capacity')\n"
                 "else:\n"
                 "    sys.exit(subprocess.call(sys.argv[2:]))\n")
        args = [sys.executable, "-c", guard, str(admission_valid_until), *args]
    command([sys.executable, str(ROOT / "scripts/grafana-maintenance.py"), "run",
             "--ttl-minutes", "10", "--reason", "DFS autoscaling", "--", *args], timeout=240)


def apply_state(state, workers, max_additions=0, admission_valid_until=None):
    """Apply controls and fill required identities without killing busy excess slots."""
    desired = state["desiredSlots"]
    excess = [worker for worker in workers if worker["slot"] > desired]
    removable = [worker for worker in excess if worker["idle"] and worker["drained"]]
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
    missing = set(range(1, desired + 1)) - {worker["slot"] for worker in workers}
    additions = min(len(missing), max_additions, MAXIMUM - len(workers))
    # Maintenance/drain operations may outlive the samples that admitted growth.
    if admission_valid_until is not None and int(time.time() * 1000) > admission_valid_until:
        additions = 0
    if additions > 0:
        # Draining high slots still own their locks but do not supply the target's
        # active capacity. Fill missing identities within this pass's admission budget.
        replicas = len(workers) + additions
        lifecycle(["docker", "compose", "up", "-d", "--no-deps", "--no-recreate", "--pull", "never",
                   "--scale", f"dfs={replicas}", "--wait", "--wait-timeout", "90", "dfs"],
                  admission_valid_until=admission_valid_until)
        workers = snapshot()
    report(state, workers)
    return workers


def reconcile(dry_run=False, windows_resources=None):
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
    now = int(time.time() * 1000)
    # Validate the signed recommendation before applying resource limits.
    state = next_state(previous, demand, now)
    guard = admission(windows_resources)
    current = previous["desiredSlots"]
    missing = len(set(range(1, current + 1)) - {worker["slot"] for worker in workers})
    growth = max(0, guard["additionalSlots"] - missing)
    if state["desiredSlots"] > current + growth:
        state = next_state(previous, {**demand, "desiredSlots": current + growth}, now)
    desired = state["desiredSlots"]
    if not dry_run:
        workers = apply_state(state, workers, guard["additionalSlots"], guard.get("validUntil"))
    return {"desiredSlots": desired, "onlineSlots": sorted(worker["slot"] for worker in workers),
            "demand": demand, "dryRun": dry_run, "resourceGuard": guard,
            "drainingSlots": sorted(worker["slot"] for worker in workers if worker["slot"] > desired)}


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
    if len(workers) != MINIMUM:
        raise ValueError("Compose must restore two baseline replicas before reset")
    state = {"protocolVersion": 1, "desiredSlots": MINIMUM, "maxSlots": MAXIMUM,
             "wakeToken": str(uuid.uuid4()), "updatedAt": int(time.time() * 1000),
             "lowSince": None, "lowDesired": None}
    # Compose ordinals do not guarantee slots 1 and 2. Fill those identities;
    # busy high slots can finish before normal reconciliation removes them.
    workers = apply_state(state, workers, MINIMUM)
    return {"reset": True, "desiredSlots": MINIMUM,
            "onlineSlots": sorted(worker["slot"] for worker in workers),
            "drainingSlots": sorted(worker["slot"] for worker in workers if worker["slot"] > MINIMUM)}


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
    parser.add_argument("--windows-resources-stdin", action="store_true")
    args = parser.parse_args()
    if args.reset_control:
        print(json.dumps(reset_control()))
        return
    if (STACK / "autoscaling.paused").exists():
        print(json.dumps({"paused": True}))
        return
    windows_resources = None
    if args.windows_resources_stdin:
        try:
            windows_resources = json.load(sys.stdin)
        except (ValueError, OSError):
            pass  # Invalid host telemetry must never grant additional capacity.
    try:
        with deployment_lock():
            print(json.dumps(reconcile(args.dry_run, windows_resources)))
    except BlockingIOError:
        print(json.dumps({"skipped": "deployment or another controller owns the lock"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "message": "Autoscaling failed; inspect host/controller health. No capacity is inferred from missing data."}), file=sys.stderr)
        raise SystemExit(1)
