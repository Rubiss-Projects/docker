# Plex settings and NAS updates

The settings below implement the owner's accepted 2026-11-16 Plex audit. They
are application preferences, persisted in the existing Plex configuration
volume; Compose does not apply this document as configuration.

| Setting | Accepted value |
| --- | --- |
| Automatically empty trash | Enabled |
| Allow media deletion | Disabled; NAS media mount remains read-only |
| Periodic library scans | Disabled after the non-arr Autopulse trigger is verified |
| Automatic filesystem scans / partial filesystem scans | Disabled; Autopulse sends targeted scans |
| Scanner low priority | Enabled |
| Prefer local/embedded metadata in TV Shows | Disabled |
| IPv6 | Disabled until end-to-end IPv6 service is validated |
| Preferred interface | `enp3s0`, the server LAN interface |
| Hardware transcoding device | Current NVIDIA RTX 2070 selection reported by Plex |

Do not copy a hardware device identifier between hosts: the native migration
changed the PCI address from `02:00.0` to `01:00.0`. Hardware decoding and encoding
remain enabled, with HDR tone mapping using `hable` and a RAM-backed `/transcode`.
Keep the accepted TLS, remote-access port, bandwidth limits, LAN subnets and
disabled Relay settings. TV episode ordering remains TheTVDB.

Sonarr and Radarr notify Autopulse after imports, upgrades, renames and deletions.
The built-in polling trigger covers video files in `/data/channels-dvr` and
`/data/videos`; it excludes Channels streaming buffers. Use arr manual import
or a targeted Autopulse request for manual additions to the main TV/movie trees.
Do not restore global scheduled scans merely to cover those two smaller libraries.

Automatic trash emptying removes obsolete Plex records, not media or torrents.
Autopulse's media anchor and path checks reduce scan requests during an outage;
they do not guarantee protection against every partial NFS failure. Plex also
normally ignores completely inaccessible library locations. Preserve an online
database backup before initial cleanup and verify the replacement remains indexed
and playable after scanning an upgraded series. Never empty unrelated libraries
as a generic fix for one show's availability.

TRaSH recommends native filesystem scans, but notes network shares may lack the
required notifications. Autopulse is the deliberate substitute here. Other Videos
is not a normal movie library and retains its personal-video scanner. Its per-library
preview flag is immaterial while global preview generation is disabled. Collection,
subtitle-analysis and remote-stream preferences with no fixed recommended value
remain unchanged.

Sources: [TRaSH Plex settings](https://trash-guides.info/Plex/Tips/Plex-media-server/),
[Plex trash](https://support.plex.tv/articles/200289326-emptying-library-trash/),
[inaccessible locations](https://support.plex.tv/articles/201447966-why-does-content-i-deleted-on-my-drive-still-show-up/),
[installed Autopulse notify implementation](https://github.com/dan-online/autopulse/blob/07d8833f845e56335ad1650de0e0e52b039417b6/crates/service/src/settings/triggers/notify.rs).
