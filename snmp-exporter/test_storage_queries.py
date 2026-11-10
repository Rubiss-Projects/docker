"""Evaluate the dashboard's actual storage queries, including failed collection."""

import argparse
import json
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
POOL = 'instance="qnap-nas",job="qnap-snmp",storagepoolID="1",storagepoolIndex="1"'
MEDIA = 'instance="qnap-nas",job="qnap-snmp",sharedFolderIndex="3",sharedFolderName="Media"'
RECOVERY = 'instance="qnap-nas",job="qnap-snmp",sharedFolderIndex="2",sharedFolderName="Recovery"'


def fixture():
    dashboard = json.loads((ROOT / "grafana/dashboards/Infrastructure/qnap-nas.json").read_text())
    queries = {panel["id"]: panel["targets"][0]["expr"] for panel in dashboard["panels"] if panel["id"] in range(9, 14)}
    expected = {
        9: [("{" + POOL + "}", 65.9167417899843)],
        10: [("storagepoolFreeSize{" + POOL + "}", 13795461814240)],
        11: [("storagepoolStatus{" + POOL + "}", 0)],
        12: [("{" + MEDIA + "}", 69.40463019394099), ("{" + RECOVERY + "}", 12.378229014575481)],
        13: [("sharedFolderFreeSize{" + MEDIA + "}", 9331587790848), ("sharedFolderFreeSize{" + RECOVERY + "}", 3853646241792)],
    }
    assert set(queries) == set(expected)
    values = [
        ("storagepoolCapacity{" + POOL + "}", 40475771797504),
        ("storagepoolFreeSize{" + POOL + "}", 13795461814240),
        ("storagepoolStatus{" + POOL + "}", 0),
        ("sharedFolderCapacity{" + MEDIA + "}", 30500000000000),
        ("sharedFolderFreeSize{" + MEDIA + "}", 9331587790848),
        ("sharedFolderCapacity{" + RECOVERY + "}", 4398046511104),
        ("sharedFolderFreeSize{" + RECOVERY + "}", 3853646241792),
    ]
    tests = []
    for state in ("fresh", "failed-scrape", "missing-collection"):
        inputs = [{"series": name, "values": f"{value} {value}"} for name, value in values]
        if state != "missing-collection":
            inputs.append({"series": 'up{instance="qnap-nas",job="qnap-snmp"}', "values": "1 1" if state == "fresh" else "0 0"})
        tests.append({"name": state, "interval": "1m", "input_series": inputs,
                      "promql_expr_test": [{"expr": expression, "eval_time": "1m",
                          "exp_samples": [{"labels": labels, "value": value} for labels, value in expected[id_]] if state == "fresh" else []}
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
