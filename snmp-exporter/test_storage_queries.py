"""Evaluate the dashboard's actual storage queries, including failed collection."""

import argparse
import json
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
POOL = 'instance="qnap-nas",job="qnap-snmp",storagepoolID="1",storagepoolIndex="1"'
MEDIA = 'instance="qnap-nas",job="qnap-snmp",sharedFolderIndex="3",sharedFolderName="Media"'


def fixture():
    dashboard = json.loads((ROOT / "grafana/dashboards/Infrastructure/qnap-nas.json").read_text())
    state_panel = next(panel for panel in dashboard["panels"] if panel["id"] == 11)
    # The vendor MIB describes conflicting QTS/QuTS hero codes. Only Ready has
    # been reconciled with this NAS; other states must retain their raw number.
    assert set(state_panel["fieldConfig"]["defaults"]["mappings"][0]["options"]) == {"0"}
    assert state_panel["fieldConfig"]["defaults"]["color"] == {"mode": "fixed", "fixedColor": "gray"}
    queries = {panel["id"]: panel["targets"][0]["expr"] for panel in dashboard["panels"] if panel["id"] in range(9, 14)}
    expected = {
        9: [("{" + POOL + "}", 65.9167417899843)],
        10: [("storagepoolFreeSize{" + POOL + "}", 13795461814240)],
        11: [("storagepoolStatus{" + POOL + "}", 0)],
        12: [("{" + MEDIA + "}", 69.40463019394099)],
        13: [("sharedFolderFreeSize{" + MEDIA + "}", 9331587790848)],
    }
    assert set(queries) == set(expected)
    values = [
        ("storagepoolCapacity{" + POOL + "}", 40475771797504),
        ("storagepoolFreeSize{" + POOL + "}", 13795461814240),
        ("storagepoolStatus{" + POOL + "}", 0),
        ("sharedFolderCapacity{" + MEDIA + "}", 30500000000000),
        ("sharedFolderFreeSize{" + MEDIA + "}", 9331587790848),
    ]
    tests = []
    for state in ("fresh", "unverified-pool-state", "failed-scrape", "missing-collection"):
        inputs = []
        for name, value in values:
            if state == "unverified-pool-state" and name.startswith("storagepoolStatus{"):
                value = -4
            inputs.append({"series": name, "values": f"{value} {value}"})
        if state != "missing-collection":
            inputs.append({"series": 'up{instance="qnap-nas",job="qnap-snmp"}', "values": "0 0" if state == "failed-scrape" else "1 1"})
        samples = dict(expected)
        if state == "unverified-pool-state":
            samples[11] = [("storagepoolStatus{" + POOL + "}", -4)]
        tests.append({"name": state, "interval": "1m", "input_series": inputs,
                      "promql_expr_test": [{"expr": expression, "eval_time": "1m",
                          "exp_samples": [{"labels": labels, "value": value} for labels, value in samples[id_]] if state in ("fresh", "unverified-pool-state") else []}
                          for id_, expression in queries.items()]})
    return {"evaluation_interval": "1m", "fuzzy_compare": True, "tests": tests}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", help="Run promtool inside an existing container without changing its server")
    args = parser.parse_args()
    if args.container:
        command = ["docker", "exec", "-i", args.container, "promtool", "test", "rules", "/dev/stdin"]
    else:
        image = yaml.safe_load((ROOT / "prometheus/docker-compose.yml").read_text())["services"]["prometheus"]["image"]
        command = ["docker", "run", "--rm", "-i", "--network", "none", "--entrypoint", "promtool", image, "test", "rules", "/dev/stdin"]
    subprocess.run(command, input=yaml.safe_dump(fixture()).encode(), check=True, timeout=120)
