#!/usr/bin/env python3
"""Run the executive dashboard's bounded, fixed-target functional probes on BEN-SERVER."""

import argparse
import concurrent.futures
import datetime as dt
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path


class ProbeFailure(Exception):
    """A fixed, non-sensitive diagnostic suitable for Kuma history."""


def inside(container, *command, script=None, user=None):
    args = ["docker", "exec", "-i"]
    if user:
        args += ["--user", user]
    return subprocess.run(
        args + [container, *command],
        input=script,
        text=True,
        capture_output=True,
        check=True,
        timeout=35,
    ).stdout


def request(url, *, timeout=7):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "homelab-health/1"}),
        timeout=timeout,
    )


def fetch_json(url):
    with request(url) as response:
        return json.load(response)


def plex():
    # Pull a playable part from Plex's catalog and read it as the Plex service user.
    inside(
        "plex",
        "sh",
        "-es",
        user="abc",
        script="""
db='/config/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db'
part=$("/usr/lib/plexmediaserver/Plex SQLite" -readonly "$db" "select file from media_parts where file like '/data/%' and deleted_at is null and size>0 order by id limit 1")
test -f "$part" && test "$(head -c 1 "$part" | wc -c)" -eq 1
""",
    )


def tuner():
    base = "http://192.168.50.130"
    status = fetch_json(base + "/status.json")
    if any(t.get("VctNumber") and t.get("NetworkRate", 0) > 0 for t in status):
        return
    jobs = fetch_json("http://127.0.0.1:8089/dvr/jobs")
    now = time.time()
    if any(
        not j.get("Skipped")
        and j.get("Time", 0) - 180 <= now <= j.get("Time", 0) + j.get("Duration", 0)
        for j in jobs
    ):
        raise ProbeFailure("Recording window; tune deferred")
    if not any(
        not t.get("VctNumber") and not t.get("TargetIP") and not t.get("Frequency")
        for t in status
    ):
        raise ProbeFailure("No idle tuner; tune deferred")
    # Auto allocation leaves existing streams alone. Close as soon as MPEG-TS sync is confirmed.
    with request(base + ":5004/auto/v2.1?duration=1") as stream:
        data = stream.read(188 * 5)
    if not any(
        all(data[i + j * 188 : i + j * 188 + 1] == b"\x47" for j in range(3))
        for i in range(188)
    ):
        raise ValueError("No transport stream")


def recording():
    config = fetch_json("http://127.0.0.1:8089/dvr")
    if not config.get("enabled") or config.get("path") != "/shares/DVR":
        raise ValueError("Recording path changed")
    inside(
        "channels-dvr",
        "sh",
        "-es",
        script="""
test "$(stat -f -c %T /shares/DVR/TV)" = nfs
file=$(mktemp /shares/DVR/TV/.health-probe.XXXXXXXX)
trap 'rm -f -- "$file"' EXIT
printf probe >"$file"
test "$(cat "$file")" = probe
""",
    )


def imports():
    for app, port in (("sonarr", 8989), ("radarr", 7878)):
        # Curl reads credentials through stdin and returns only the queue to this process.
        page = 1
        while page <= 20:
            raw = inside(
                app,
                "sh",
                "-es",
                "--",
                str(port),
                str(page),
                script=r"""
key=$(sed -n 's:.*<ApiKey>\(.*\)</ApiKey>.*:\1:p' /config/config.xml)
test -n "$key"
printf 'header = "X-Api-Key: %s"\n' "$key" | curl -fsS --max-time 8 --config - "http://localhost:$1/api/v3/queue?page=$2&pageSize=200&includeUnknown=false"
""",
            )
            result = json.loads(raw)
            for item in result["records"]:
                if (
                    item.get("trackedDownloadState")
                    in ("importBlocked", "importFailed")
                    or item.get("trackedDownloadStatus") == "error"
                ):
                    raise ProbeFailure(app + " reports a blocked import")
            if page * 200 >= result["totalRecords"]:
                break
            page += 1
        else:
            raise ValueError("Queue coverage exceeded")


def libraries():
    inside(
        "calibre",
        "python3",
        "-",
        user="abc",
        script="""
import sqlite3
from pathlib import Path
db=sqlite3.connect('file:/books/metadata.db?mode=ro',uri=True)
folder,name,fmt=db.execute('select b.path,d.name,d.format from books b join data d on d.book=b.id where b.id=28 and d.format=? limit 1',('EPUB',)).fetchone()
with (Path('/books')/folder/(name+'.'+fmt.lower())).open('rb') as f:
    if not f.read(1): raise ValueError()
""",
    )
    inside(
        "audiobookshelf",
        "node",
        "-",
        script="""
const fs=require('node:fs');
const db=new(require('node:sqlite').DatabaseSync)('/config/absdatabase.sqlite',{readOnly:true});
const row=db.prepare("select audioFiles from books where length(audioFiles)>3 order by id limit 1").get();
const file=JSON.parse(row.audioFiles)[0].metadata.path;
const fd=fs.openSync(file,'r');
if(fs.readSync(fd,Buffer.alloc(1),0,1,0)!==1) process.exitCode=1;
fs.closeSync(fd);
""",
    )


def vault():
    row = inside(
        "bitwarden-db-1",
        "sh",
        "-ec",
        """PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=5000" exec psql -XAtq -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'select 1 from "__EFMigrationsHistory" limit 1' """,
    )
    if row.strip() != "1":
        raise ValueError("No migration record")


def backup():
    # Lazywarden runs at midnight on the 23rd. Allow 24 hours to finish.
    inside(
        "lazywarden",
        "/app/venv/bin/python",
        "-",
        script="""
import datetime as dt,hashlib,os
from pathlib import Path
if os.environ['CRON_SCHEDULE']!='0 0 23 * *': raise ValueError('Schedule changed')
now=dt.datetime.now()
due=now.replace(day=23,hour=0,minute=0,second=0,microsecond=0)
if now<due+dt.timedelta(days=1): due=(due.replace(day=1)-dt.timedelta(days=1)).replace(day=23)
archive=max(Path('/root/lazywarden/backup-drive').glob('bw-backup_*.zip'),key=lambda p:p.stat().st_mtime)
if not due.timestamp()<=archive.stat().st_mtime<=now.timestamp() or not archive.stat().st_size: raise ValueError()
with archive.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
if digest!=Path(str(archive)+'.hash').read_text().strip(): raise ValueError()
""",
    )


def accessory():
    inside(
        "homepage",
        "node",
        "-",
        script="""
(async()=>{
 const base='https://homebridge.benlawson.dev/api';
 const login=await fetch(base+'/auth/login',{method:'POST',redirect:'error',headers:{'content-type':'application/json'},body:JSON.stringify({username:'rubiss',password:process.env.HOMEPAGE_VAR_HOMEBRIDGE_PI_PASSWORD})});
 if(!login.ok) throw Error();
 const {access_token}=await login.json();
 const response=await fetch(base+'/accessories/053abb5f7b83adff89950611d806d565e1cb9aa3c317b2a1e52fc9b38df53cfa',{redirect:'error',headers:{authorization:'Bearer '+access_token}});
 if(!response.ok) throw Error();
 const sensor=await response.json();
 if(sensor.humanType!=='Contact Sensor' || ![0,1].includes(sensor.values.ContactSensorState)) throw Error();
})().catch(()=>process.exitCode=1)
""",
    )


def workflow():
    inside(
        "n8n",
        "node",
        "-",
        script="""
const db=new(require('node:sqlite').DatabaseSync)(process.env.N8N_USER_FOLDER+'/.n8n/database.sqlite',{readOnly:true});
const row=db.prepare("select status, (julianday('now')-julianday(stoppedAt))*86400 as age from execution_entity where workflowId=? and stoppedAt is not null order by id desc limit 1").get('sundayEdgeAutoscale1');
if(row?.status!=='success' || row.age===null || row.age<0 || row.age>180) process.exitCode=1;
""",
    )


def internet():
    for url, code in [
        ("https://connectivitycheck.gstatic.com/generate_204", 204),
        ("https://www.cloudflare.com/cdn-cgi/trace", 200),
    ]:
        try:
            with request(url) as response:
                if (
                    response.status == code
                    and response.geturl() == url
                    and (code == 204 or b"fl=" in response.read(256))
                ):
                    return
        except OSError:
            continue
    raise ValueError("Both external destinations failed")


def tunnel():
    runs = fetch_json(
        "https://api.github.com/repos/Rubiss-Projects/docker/actions/workflows/probe-tunnel.yml/runs?branch=main&status=completed&per_page=1"
    )
    run = runs["workflow_runs"][0]
    completed = dt.datetime.fromisoformat(run["updated_at"])
    if (
        run["conclusion"] != "success"
        or not 0 <= time.time() - completed.timestamp() <= 7200
    ):
        raise ValueError("External probe failed or stale")


CHECKS = {
    "Plex library read": plex,
    "HDHomeRun tune": tuner,
    "DVR recording path": recording,
    "Completed import": imports,
    "Library read": libraries,
    "Database-backed vault read": vault,
    "Last successful backup": backup,
    "Accessory control": accessory,
    "Workflow execution": workflow,
    "Internet reachability": internet,
    "External tunnel route": tunnel,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push-file", type=Path)
    args = parser.parse_args()
    tokens = json.loads(args.push_file.read_text()) if args.push_file else {}
    if args.push_file and set(tokens) != set(CHECKS):
        raise ValueError("Incomplete monitor configuration")

    def check(item):
        name, probe = item
        try:
            probe()
            status, message = "up", "Functional check passed"
        except ProbeFailure as exc:
            status, message = "down", str(exc)
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ):
            status, message = "down", "Functional check failed"
        print(name, status, flush=True)
        if args.push_file:
            url = "http://127.0.0.1:3001/api/push/" + urllib.parse.quote(
                tokens[name]["token"], safe=""
            )
            with request(
                url + "?" + urllib.parse.urlencode({"status": status, "msg": message})
            ) as response:
                if not json.load(response).get("ok"):
                    raise RuntimeError("Kuma rejected probe result")
        return status

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        statuses = list(executor.map(check, CHECKS.items()))
    return 1 if not args.push_file and "down" in statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
