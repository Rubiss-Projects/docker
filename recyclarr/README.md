# Media quality and language policy

Recyclarr maintains TRaSH profiles; Seerr defaults and existing Sonarr/Radarr
assignments must also point to those profiles. A successful sync alone does not
migrate the library.

- Regular TV: `WEB-1080p (Alternative)`, with the guide's 720p/Blu-ray/HDTV
  fallbacks. Both managed regular TV profiles require English audio and do not
  require an additional original-language track.
- Regular movies: `HD Bluray + WEB`, requiring English audio.
- Anime: the service's `[Anime] Remux-1080p` guide profile. Sonarr has a separate
  Seerr anime default. Movies use a Seerr override rule scoped to the Radarr
  service and TMDB's anime keyword (`210024`), selecting the anime profile.
  Ordinary animation does not match that rule. Check metadata/manual profile
  selection if an anime movie is missing its keyword.
- `Dragon Ball Super Beerus - Subs then Dub` is an existing, separately managed
  exception. Do not migrate its series or reset its custom scores.

Multilingual releases containing English are acceptable for regular media.
Non-anime original-language audio without English is not, even with English
subtitles. Anime uses the guide's translated-release filters; subtitles still
need verification after import because release names cannot prove their presence.

## Radarr language override

Recyclarr 8.8.1 cannot override a guide-backed profile's language in YAML. The
supplemental resource in `config/overrides` copies the official `HD Bluray + WEB`
profile and changes only `language` from `Original` to `English`. This avoids
rejecting English dubs of foreign films or resetting the policy on the daily sync.
Custom formats, scores and default groups continue to sync from upstream.

The profile snapshot comes from TRaSH Guides commit
`fa08c05a7471111ab4451280d6a727d1ae83b8af` (2026-11-15). When refreshing this
override, compare it against upstream `docs/json/radarr/quality-profiles/hd-bluray-web.json`
and preserve only the English language difference. Its quality ordering is a
snapshot until that refresh. Remove the override when Recyclarr supports a
language setting directly.

## Verification and preservation

Preview with `docker exec recyclarr recyclarr sync --preview`, inspect language
scores, then sync. Verify profile IDs in Seerr and all existing series/movies;
preserve the Dragon Ball exception. Do not trigger a library-wide search as part
of a profile migration.

Audit actual audio-track metadata separately from release-title language labels.
Unknown or missing audio tags are unverified, not proof of English audio. Keep
started torrents and all data; stopping a rejected torrent is allowed only after
confirming zero downloaded bytes, zero valid/unchecked data and no transfer rate.
