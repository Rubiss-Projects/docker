# Autopulse

Sonarr and Radarr notify Autopulse after imports, upgrades, renames and deletions.
Autopulse persists requests in SQLite and sends targeted updates to Plex without
relying on NAS filesystem notifications. Requests wait 60 seconds before processing.

This is an internal BEN-SERVER service on proxynet, with no published port or SWAG
route. Homepage and Uptime Kuma monitor its public `/stats` endpoint. Its API uses
basic authentication. No dedicated Homepage widget is available.

## Native setup

Secrets are stored in the git-crypt encrypted `.env.secret`: `AUTOPULSE_PASSWORD`
is a random webhook password and `PLEX_TOKEN` is the existing server token.
Never print rendered Compose configuration or commit plaintext credentials.

Create private `data/` storage owned by UID/GID 1000. On the verified NAS mount,
create `/srv/Media/.autopulse.anchor`; a missing anchor pauses updates. Mount NAS
media read-only at `/data`, matching Plex and the arr apps so rewrites are unneeded.
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

Use username `autopulse` and the password from `.env.secret`. Enable import,
upgrade, rename, and supported series/movie/file deletion events. Leave grab
disabled because the media has not reached its final library path. Test and save.
Avoid duplicate Plex update connections on the same events.

Keep Plex automatic filesystem scans disabled and hourly periodic scans enabled
for Channels recordings, Other Videos and additions outside the arr apps. Keep
automatic trash emptying disabled to preserve metadata during NAS outages.
Seerr continues its existing arr progress polling and five-minute Plex scans.

## Verification and backout

Check container health and logs, test both arr webhooks, then submit a real import
payload (or an authenticated manual trigger for an existing file) and verify the
persisted request completes and Plex lists the item. A test webhook alone does
not enqueue media. Scan each Plex library once to recover the pre-trigger backlog.

To back out, disable the two Autopulse connections and stop the service using the
native adapter. Retain SQLite state and encrypted secrets. Periodic Plex scans
continue covering new media.

References: [Autopulse v2.0.0](https://github.com/dan-online/autopulse/tree/v2.0.0),
[TRaSH Plex settings](https://trash-guides.info/Plex/Tips/Plex-media-server/).
