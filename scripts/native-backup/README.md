# Native application backups

Recurring backup integration is in progress. These producers replace one-off
migration capture scripts; installing this directory alone enables no schedule.
The original migration archives and accepted independent restores remain intact.

## Bitwarden Lite recovery set

`vault.py` covers the admitted native Bitwarden Lite PostgreSQL backend and its
application volume. This is the Lite deployment, rather than Vaultwarden. The
PostgreSQL image/configuration and application volume are admitted explicitly;
changed database backends, image identities or mount layouts require review.

The producer holds an exported read-only PostgreSQL snapshot until both its
custom-format dump and complete per-table row-content/count inventory finish.
Identity material, data-protection keys, configuration, licenses and attachments
must remain stable across that database checkpoint and confined file copy. It
excludes only the root application log directory, preserves supported ownership,
mode, timestamps and xattrs, and rejects symlinks and special files. The paired
files/database are not an atomic filesystem/database transaction; concurrent
application-file changes fail admission rather than claiming a matching set.

After the NAS restore, verification restores every table into the same pinned
PostgreSQL binary in a new network-isolated helper. It runs as UID 999 with no
capabilities, a read-only root, no host ports/bind mounts, fixed resource limits,
and private memory-backed database storage. An explicit tmpfs masks the image's
declared data volume. It never starts a Bitwarden application identity. Every
restored table count and content digest must match before a success heartbeat.
The producer also saves role definitions/password verifiers and current runtime
database credentials privately inside the encrypted recovery set. Roles, grants,
role settings, object ownership and ACL inventories must remain stable across
capture and match the restored database. The verifier replays roles and restores
the database with ownership/ACLs, then authenticates the captured application
password over its isolated loopback using SCRAM. Custom tablespaces, extra
application databases and a preexisting `verifier` account require separate
admission. Successful helpers are removed after a clean
exit. Failed or uncertain helpers and their intent remain for reconciliation;
any retained helper blocks a new capture. Never clear that admission by blindly
re-running the job.

Use `scope: vault`, its own private `stateDirectory` and human-only push monitor,
and the same admitted encrypted repository. Install `vault_security.py` before
`vault.py`, and both before replacing
the shared runner. The supplied timer runs at 03:20 Eastern with up to ten
minutes of jitter; it remains disabled until an actual fresh production capture,
full encrypted repository read, isolated restore and real monitor heartbeat pass.
Retention uses the exact `native-recurring,scope=vault` group and preserves every
other scope and original migration snapshot. Existing Portainer and n8n schedules
remain independent.

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

## Encrypted repository runner

`repository.py` connects the fresh Portainer producer to an already initialized
encrypted NAS repository. Copy `repository.example.json` into a root-owned 0600
configuration, substituting the independently verified repository ID and pinned
bbolt binary path. The runner refuses another NAS/share/filesystem, a local
fallback, insufficient headroom, or an unexpected repository ID.

Before enabling its timer, create an existing Uptime Kuma **push monitor with
human notifications** and save its local `http://127.0.0.1:3001/api/push/TOKEN`
URL in the protected `pushUrlFile`. Configure a heartbeat interval longer than
the daily interval plus timer jitter and the two-hour job ceiling (for example
28 hours). Prove both a failure and recovery notification. An unavailable sender
fails the job; the monitor's missing-heartbeat detection also covers a stopped
host or a process killed before it can report failure. This is alerting only;
never connect the monitor to a container/host restart webhook.

The supplied service/timer require explicit installation and activation. Create
`/var/lib/native-backup` as root-owned 0700, install the Python modules read-only
under `/usr/local/lib/native-backup`, and preserve the credential file separately.
The service uses a private temporary directory and makes only its state and NAS
mount writable. `systemd-analyze verify` must pass before installation.

```sh
sudo python3 -B /usr/local/lib/native-backup/repository.py /etc/native-backup/portainer.json
```

Each locked invocation creates a new private capture and records its phase.
Before the API request, the runner durably writes `capture-attention.json` and
syncs its directory. It removes that marker only after the completed capture's
next phase is durably recorded. SIGTERM, SIGKILL and a host interruption therefore
leave admission blocked until the retained intent/partial is reconciled. Do not
remove that marker just to make a failed timer green. The runner never stops,
restarts, recreates, or starts an application container.

Success requires a fresh supported capture, encrypted backup, full repository
data check, verified restore, matching archive SHA-256, and another full archive
and bbolt check. The restored copy stays private and no restored application is
started. Logs and captures remain for reconciliation; this initial runner
does not automatically remove private local job directories.

Retention keeps 14 daily, eight weekly and 12 monthly points for the exact
`ben-server`/`native-recurring`/`scope=portainer` group. It first produces a dry-run
plan. `applyRetention` defaults to false for admission. After the actual fixture
and restore acceptance, true enables forgetting only the validated immutable IDs,
with at least one owned snapshot retained. The runner verifies every unselected
snapshot remains, prunes unreferenced data with a 1 GiB repack bound, and performs
another full data check. Original migration snapshots lack both recurring tags
and cannot enter this policy. See the upstream [tag filter and retention
semantics](https://restic.readthedocs.io/en/stable/060_forget.html).

## n8n producer and schedule

Set `scope` to `n8n` in a separate root-owned configuration. Use its own
`stateDirectory` and human-only push monitor; omit `bbolt`. Install
`confined_files.py` and `n8n.py` alongside `portainer.py` before replacing the
shared `repository.py`. Existing
Portainer configurations without a scope retain their original behavior.

The n8n producer checks the running container's admitted native mount and SQLite
configuration. It snapshots committed database state through SQLite's online
backup API, finalizes a standalone database, and captures the unchanged
file-persisted encryption key, binary data, custom nodes, SSH and recovery files
under `/srv/Docker/n8n/config/{.n8n,recovery}`. It excludes event/crash logs and
database sidecars. It neither starts n8n nor changes workflow activation.
Individual supporting files must stay stable while copied; the database and all
supporting files are not a cross-file atomic snapshot. An external key or another
database backend requires a separately admitted producer.

Capture and restore verification require root and Linux `openat2` support;
unsupported kernels fail closed. Source and destination operations use directory
file descriptors with beneath/no-symlink/no-magic-link resolution. Stored symlink
objects are preserved, but traversal and writes never follow them. SQLite runs in
a separate child chrooted to the pinned data tree, retaining only DAC override
for mixed file ownership. It closes inherited descriptors, drops capability
bounds, locks out root privilege recovery and sets no-new-privileges. Its online
snapshot is serialized through a pipe, so the live WAL reader cannot reach the
host filesystem and the root writer uses only confined destination handles.
Linux CI runs the capture tests with sudo to exercise that actual confinement.

The restored capture must match every file digest, ownership, mode, timestamp,
xattr and symlink target, pass SQLite integrity checks and match all table row
counts, including the required n8n application tables. Capturing a key is not a
credential-decryption test: require separate independent application recovery
acceptance before enabling the supplied service/timer. The timer runs at 04:20
America/New_York plus jitter, before the Portainer job. Install and admit it
explicitly, following the same repository, restore, retention and alert gates.

`scope=n8n` snapshots have their own 14-daily/8-weekly/12-monthly retention group;
Portainer and original migration snapshots cannot enter that policy. Installing
these files alone enables no schedule. The runner supports Portainer, n8n and
Bitwarden; recurring protection for other critical scopes remains incomplete.

## Host/bootstrap capture primitives (integration pending)

`host_files.py` captures an individually admitted tree through confined file
descriptors. It recognizes SQLite by its header, including databases without
standard extensions, and snapshots committed state through SQLite's online
backup API. It preserves regular-file metadata and symlink objects without
following them. Unadmitted special files fail capture. Individual database
snapshots and supporting files are not a cross-database or whole-host atomic
snapshot.

`sqlite_snapshot_file` writes the confined child's output directly to an
exclusive destination descriptor. The parent does not buffer another copy of a
large database. The source and output bounds are 1 GiB, with a 3 GiB child address
space limit and a 150-second deadline. Larger databases require separate
admission. The host filesystem root cannot be used as the SQLite sandbox.

These primitives do not yet select the full host roots, capture the Git/secret/
runtime bootstrap supplement, or register a recurring producer and timer. Keep
their plaintext capture inside private job directories and require encrypted
NAS backup, full repository read and restored-file/database verification before
enabling host protection. Existing schedules remain independent.
