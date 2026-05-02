# Bookshelf Import Recovery

## What Changed

The durable fix was applied on the Calibre side, not in Bookshelf.

- `calibre/docker-compose.yml` now mounts `./custom-services.d:/custom-services.d:ro`.
- `calibre/custom-services.d/calibre-server` now starts the Calibre content server under LinuxServer `s6` on container startup.

The custom service runs:

```bash
calibre-server \
  --listen-on 0.0.0.0 \
  --port 8081 \
  --enable-auth \
  --userdb /config/.config/calibre/server-users.sqlite \
  --log /config/calibre-server.log \
  --access-log /config/calibre-server-access.log \
  /books
```

## Why This Was Needed

Bookshelf depends on the Calibre content server at `http://calibre:8081` for both manual imports and library rescans.

Before this change, the Calibre container could come up without a working content server even though the GUI configuration had server autostart enabled. In practice that left Bookshelf with repeated import failures such as connection refused errors against `calibre:8081`.

Once the content server was restored as a supervised service, Bookshelf could talk to Calibre reliably again and imports started working.

## What Was Recovered

These imports were repaired and verified in Bookshelf by checking that a `bookfile` row exists after import:

- The Emperor's Soul
- Warbreaker
- The Way of Kings
- Rhythm of War
- The Alloy of Law
- Edgedancer
- Shadows of Self
- Dawnshard
- Words of Radiance

Important detail:

- Real execution uses `POST /api/v1/command` with `name: "ManualImport"` and a populated `files` array.
- `GET/POST /api/v1/manualimport` is useful for previewing candidates, but it is not the final execution path.

## Current Queue State

At the end of this recovery pass the queue still shows three rows:

- `James A Novel`
- `The Frozen River`
- `Words of Radiance`

Those rows are not all active import failures anymore.

- `James A Novel` is already imported. Manual import preview shows only duplicate/non-upgrade files.
- `The Frozen River` is already imported. Manual import preview shows only duplicate/non-upgrade files.
- `Words of Radiance` now has a real Bookshelf `bookfile`, but the old failed queue state is still stuck on the tracked download.

## Remaining Problems

### 1. Stale queue rows cannot be cleared safely through the current API path

Two queue cleanup paths were tested against the running Bookshelf fork:

- `DELETE /api/v1/queue/{id}?removeFromClient=false`
- `DELETE /api/v1/queue/{id}?removeFromClient=false&changeCategory=true`

Current behavior:

- `removeFromClient=false` throws `System.NullReferenceException` in `IgnoredDownloadService.IgnoreDownload(...)`.
- `changeCategory=true` throws `System.NotSupportedException: Transmission does not support marking items as imported`.

Because this instance uses Transmission and the safer ignore path is broken in the fork, the stale queue rows could not be removed without risking unwanted download-client side effects.

### 2. Full `RescanFolders` still fails on a ghost Calibre file

`RescanFolders` still fails on this path:

```text
/data/books/Brandon Sanderson/The Emperor's Soul_ 10th Anniversary Edition (53)/The Emperor's Soul_ 10th Anniversary Editi - Brandon Sanderson.epub
```

What was verified:

- That stale path no longer exists in the Bookshelf SQLite dump.
- `calibredb --with-library /books list --for-machine` does not show book id `53` anymore.
- Bookshelf still receives the stale remote path during library scans and then fails when it tries to read the missing file locally.

The practical conclusion is that a stale Calibre-side path is still being surfaced during scan operations even though the main Bookshelf DB no longer references it.

## Operator Notes

- If new import warnings appear, preview them with `/api/v1/manualimport`, then execute with `POST /api/v1/command` and `name: "ManualImport"`.
- Do not assume a successful `ManualImport` command means the import finished correctly. Always verify with `/api/v1/bookfile?bookId=...`.
- Do not rely on queue deletion for completed Transmission-backed items in this fork until the `IgnoredDownloadService` null-reference bug is fixed.
- If full rescans are needed, the next investigation target is the Calibre content server path list for the deleted Emperor's Soul test record.