# Native application backups

Recurring backup integration is in progress. These producers replace one-off
migration capture scripts; installing this directory alone enables no schedule.
The original migration archives and accepted independent restores remain intact.

## Portainer online producer

`portainer.py` uses Portainer's supported administrator backup API with the
existing resolved Homepage widget key. It does not create credentials, change
authentication, or stop/restart the container. The archive contains private keys
and database state: keep the parent directory root-owned mode 0700, and protect
the completed capture with the admitted encrypted NAS repository.

```sh
sudo python3 scripts/native-backup/portainer.py capture /var/lib/native-backup/unique-capture --bbolt /path/to/verified/bbolt
```

The destination must not exist. A retained intent or partial archive must be
reconciled before another request; a timeout does not authorize a retry. An
ordinary new scheduled capture uses a new destination, with an outer lock to
prevent overlapping captures. Repository capture and retention are separate
steps; `capture.json` explicitly records that encryption is still pending.

Vendor archives legitimately contain absolute names. The verifier never extracts
them to those paths: it streams/hashes every regular member and writes only the
root database into a confined temporary directory. It rejects traversal, links,
devices, duplicate names and oversized payloads, reads the complete gzip stream,
and requires the pinned, independently verified bbolt verifier's full consistency
check. Keep the verifier read-only; the accepted tool is bbolt v1.5.0.

An existing retained archive can be verified without contacting Portainer:

```sh
sudo python3 scripts/native-backup/portainer.py verify /private/backup.tar.gz --bbolt /path/to/verified/bbolt
python3 -m unittest discover -s scripts/native-backup -p 'test_*.py'
```

This file/database proof does not start a restored Portainer identity. Full
recurring coverage, scheduling, encrypted repository admission, retention and
failure alerts remain migration requirements until separately installed and
verified. Do not point a timer at previously captured migration payloads and
report them as fresh application backups.
