# Channels browser playback compatibility

Channels DVR 2026.08.07.0346 bundles HLS.js 0.13.2. Live HDHomeRun streams
reproduced Firefox `MEDIA_ERR_DECODE` / `SampleIterator::GetNext(): Sample data
read failed` after a short transport-stream segment, including with native Linux
session storage and successful HTTP responses. A simultaneous test using HLS.js
1.6.16 continued through the same segments. This adapter uses the maintained
1.6 patch line (1.6.19).

The Channels SWAG virtual host injects a locally served HLS.js library and this
VideoJS source handler after the original UI bundle. The existing guide, player
controls, authentication, stream URLs, and server transcoding remain in use.
The adapter restores `window.Hls` and skips installation unless the bundled
version is exactly 0.13.2. Safari's native HLS path is preserved.

This affects `https://channels.benlawson.dev`, not direct port 8089. Remove the
injection and `/channels-player/` location after Channels ships a corrected
player. No proprietary Channels bundle is modified or redistributed.

## Vendored dependency

- HLS.js 1.6.19, MIT licensed; see `LICENSE.hls.js`.
- Source: https://cdn.jsdelivr.net/npm/hls.js@1.6.19/dist/hls.min.js
- Upstream: https://github.com/video-dev/hls.js/releases/tag/v1.6.19
- The minified file is unmodified. Preserve its license notice when updating.
- SHA-256: `72b87a6e58db623feca73ab370970c1126ec06eb3dcd0a67fd14b47b6340b820`.

After changing the adapter, bump its URL filename, validate `nginx -t`, and test
the actual VideoJS handler with live HDHomeRun and IPTV streams, seeking, pause,
resume, and disposal. A bare HLS.js test is insufficient to validate integration.
