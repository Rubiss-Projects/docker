# Media quality and language policy

Recyclarr maintains TRaSH profiles; Seerr defaults and existing Sonarr/Radarr
assignments must also point to those profiles. A successful sync alone does not
migrate the library.

- Regular TV: `WEB-1080p (Alternative)`, with the guide's 720p/Blu-ray/HDTV
  fallbacks. Both managed regular TV profiles require English audio and do not
  require an additional original-language track.
- Regular movies: `HD Bluray + WEB`, requiring English audio.
- Existing 1080p remux movies: `Remux + WEB 1080p`. Existing 2160p movies:
  `UHD Bluray + WEB`, or `Remux + WEB 2160p` for remuxes. These profiles also
  require English audio. Keep Seerr's default on the regular HD profile.
- Series with existing 2160p episodes: `WEB-2160p (Alternative)`, requiring
  English audio and retaining HD fallbacks. The local ordering override puts
  `Bluray-2160p` above `WEB 1080p` so an HD WEB release cannot replace UHD Blu-ray.
- Anime: the service's `[Anime] Remux-1080p` guide profile. Sonarr has a separate
  Seerr anime default. Movies use a Seerr override rule scoped to the Radarr
  service and TMDB's anime keyword (`210024`), selecting the anime profile.
  Ordinary animation does not match that rule. Check metadata/manual profile
  selection if an anime movie is missing its keyword.
  Radarr's local anime profile ordering keeps disabled UHD qualities above HD
  tiers to preserve an existing UHD movie without enabling new UHD anime grabs.
  Anime language rules, scores and the guide's combined HD tiers stay unchanged.
- `Dragon Ball Super Beerus - Subs then Dub` is an existing, separately managed
  exception. Do not migrate its series or reset its custom scores.

Multilingual releases containing English are acceptable for regular media.
Non-anime original-language audio without English is not, even with English
subtitles. Anime uses the guide's translated-release filters; subtitles still
need verification after import because release names cannot prove their presence.

## Profile overrides

Recyclarr 8.8.1 cannot override a guide-backed profile's language in YAML. The
supplemental resources in `config/overrides/radarr` copy the four regular movie
profiles and change only `language` from `Original` to `English`. This avoids
rejecting English dubs of foreign films or resetting the policy on the daily sync.
Custom formats, scores and default groups continue to sync from upstream.

The profile snapshots come from TRaSH Guides commit
`fa08c05a7471111ab4451280d6a727d1ae83b8af` (2026-11-15). When refreshing these
overrides, compare each file against its upstream counterpart in
`docs/json/{radarr,sonarr}/quality-profiles/`. Preserve only the English language
differences for regular Radarr profiles, disabled UHD placement for Radarr's
anime profile, and the `Bluray-2160p` placement for Sonarr. Their quality
ordering is a snapshot until that refresh. Remove the regular-movie language
overrides when Recyclarr supports a language setting directly; retain the
quality-preservation overrides while the upstream order would permit downgrades.

## Assign profiles without quality downgrades

Profile order affects existing files even when their quality is disabled. The
regular HD movie profile ranks disabled remux/UHD types below allowed HD encodes;
moving every movie onto it can make an encode look like an upgrade over a remux.
Likewise, the upstream alternative UHD TV profile prefers 1080p WEB over UHD
Blu-ray, which conflicts with preserving existing resolution here.

Before a bulk reassignment, inventory every movie file and every episode file,
including mixed-quality seasons. Preserve anime and Dragon Ball assignments.
For other titles, choose the profile matching the highest existing resolution
and remux type using the mapping above. Leave missing/ordinary HD titles on the
regular defaults; existing SD and 720p files can still upgrade to HD.

After syncing and assigning, check the actual API profile ordering: no allowed
lower-resolution quality may outrank an existing file, and no allowed encode of
the same or lower resolution may outrank an existing remux. Also inspect release
rejection reasons for affected titles using interactive searches only. Do not
trigger automatic download searches as part of this migration. Existing files
and seeding torrents must remain intact.

The 2026-11-15 audit corrected 125 regular 1080p remux movies, nine regular UHD
encode/WEB movies, one UHD remux movie, and three series containing eight UHD
episodes. The anime ordering correction protects the existing UHD copy of
Dragon Ball Super: Super Hero without changing the separate Beerus TV exception.
It covered all 382 movie files and 7,686 episode files; lower-resolution fallback
files did not require reassignment.

## Exclude a mistaken download without interrupting seeding

For a confirmed wrong-title release, blocklist it from the application's queue
with `removeFromClient=false` and `skipRedownload=true`. Replace that torrent's
application label with a nonempty `seeding-only-wrong-movie` label, preserving
other labels, its data path, and seeding state. Transmission 4's label filtering
then excludes it from completed-download handling. An empty label is insufficient
because the application may fall back to matching the download directory.

Verify the queue entry stays absent after completed-download handling runs and
the original library file remains unchanged. Do not disable manual-intervention
notifications globally or remove the torrent/data to silence an alert.

## Verification and preservation

Preview with `docker exec recyclarr recyclarr sync --preview`, inspect language
scores, then sync. Verify profile IDs in Seerr and all existing series/movies;
preserve the Dragon Ball exception. Do not trigger a library-wide search as part
of a profile migration.

Audit actual audio-track metadata separately from release-title language labels.
Unknown or missing audio tags are unverified, not proof of English audio. Keep
started torrents and all data; stopping a rejected torrent is allowed only after
confirming zero downloaded bytes, zero valid/unchecked data and no transfer rate.
