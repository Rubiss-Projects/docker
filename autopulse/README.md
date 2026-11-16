# Autopulse

Sonarr, Radarr, Bookshelf and Bookshelf Audio notify Autopulse after imports,
upgrades, renames and deletions. Autopulse persists requests in SQLite and sends
targeted updates to Plex and Audiobookshelf without
relying on NAS filesystem notifications. Requests wait 60 seconds before processing.

This is an internal BEN-SERVER service on proxynet, with no published port or SWAG
route. Homepage and Uptime Kuma monitor its public `/stats` endpoint. Its API uses
basic authentication. No dedicated Homepage widget is available.

## Native setup

Secrets are stored in the git-crypt encrypted `.env.secret`: `AUTOPULSE_PASSWORD`
is a random webhook password and `PLEX_TOKEN` is the existing server token.
`AUDIOBOOKSHELF_TOKEN` authenticates library reads and watcher updates using the
existing Audiobookshelf integration token.
Never print rendered Compose configuration or commit plaintext credentials.

Create private `data/` storage owned by UID/GID 1000. On the verified NAS mount,
create `/srv/Media/.autopulse.anchor`; a missing anchor pauses updates. Mount NAS
media read-only at `/data`, matching Plex and the arr apps so rewrites are unneeded.
Audiobookshelf uses `/books` and `/audiobooks`, so its target removes the `/data/`
prefix. Path checks still run against Autopulse's original `/data` paths. Trigger
exclusions route video events only to Plex and book events only to Audiobookshelf.
The native policy must explicitly admit this stack, its bind sources, and the
existing proxynet identity before deployment:

```sh
python3 scripts/native-deploy/compose.py --admit autopulse
python3 scripts/native-deploy/compose.py --stack autopulse -- up -d
```

The service runs as UID/GID 1000 with a read-only root filesystem, no capabilities,
and no Docker socket. Only its local SQLite directory is persistent writable state.

## Arr connections

Under Settings → Connect, create a Webhook named `Autopulse` with method POST:

- Sonarr: `http://autopulse:2875/triggers/sonarr`
- Radarr: `http://autopulse:2875/triggers/radarr`
- Bookshelf: `http://autopulse:2875/triggers/bookshelf` (Readarr trigger)
- Bookshelf Audio: `http://autopulse:2875/triggers/bookshelf-audio` (Readarr trigger)

Use username `autopulse` and the password from `.env.secret`. Enable import,
upgrade, rename, and supported series/movie/file deletion events. Leave grab
disabled because the media has not reached its final library path. Test and save.
Avoid duplicate Plex update connections on the same events.
For Bookshelf, enable release import, upgrade, rename, author/book deletion and
book-file deletion (including deletion for upgrade). Leave grab, author-added,
health and application events disabled. Keep the existing Seerr availability
webhooks enabled; those serve a different purpose.

Keep Plex automatic filesystem scans and periodic scans disabled. The
`non-arr-video` notify trigger polls Channels recordings and Other Videos for
video changes; the polling backend works with NFS without filesystem events.
Autopulse v2 polls every 10 seconds, so keep this limited to these small trees,
not the full TV/movie library or downloads. Streaming buffers, logs and images
are excluded. New files pass through the same 60-second batching, media anchor
and path checks as imports before a targeted Plex update is sent.

Enable Plex automatic trash emptying for obsolete library entries. Plex media
deletion stays disabled and `/data` stays read-only; seeding data is untouched.
The anchor reduces scans during NAS outages but cannot make Plex cleanup atomic
with storage health. A partial storage failure can still remove library records.
Do manual TV/movie additions through Sonarr/Radarr import, or explicitly trigger
Autopulse for their final library path. Seerr's existing five-minute Plex scans
poll availability; they do not replace filesystem scans.

See [Plex settings](../plex/settings-policy.md) for the accepted settings and
the deliberate exceptions to TRaSH's generic recommendations.

## Verification and backout

Check container health and logs, test both arr webhooks, then submit a real import
payload (or an authenticated manual trigger for an existing file) and verify the
persisted request completes and Plex lists the item. A test webhook alone does
not enqueue media. Scan each Plex library once to recover the pre-trigger backlog.
For each Bookshelf instance, submit a Readarr `Download` payload containing an
existing imported `bookFiles[].path`, verify its event completes only against
Audiobookshelf, and confirm the item appears in the appropriate library. Scan
Audiobookshelf's Audio Books and Ebooks libraries once for existing downloads.

To back out, restore hourly periodic Plex scans before disabling Autopulse
connections or stopping the service through the native adapter. Disable automatic
trash emptying first if reverting to the former NAS-outage policy. Retain SQLite
state and encrypted secrets.

References: [Autopulse v2.0.0](https://github.com/dan-online/autopulse/tree/v2.0.0),
[TRaSH Plex settings](https://trash-guides.info/Plex/Tips/Plex-media-server/).
