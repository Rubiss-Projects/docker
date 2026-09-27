/* Channels' VideoJS controls with a newer MPEG-TS demuxer. */
(() => {
  "use strict";
  const Hls = window.Hls;
  const legacyHls = window.ChannelsLegacyHls;
  window.Hls = legacyHls;
  delete window.ChannelsLegacyHls;

  // Retire automatically when Channels updates its bundled player.
  if (legacyHls?.version !== "0.13.2" || Hls?.version !== "1.6.19" || !Hls.isSupported()) return;
  const Html5 = window.videojs?.getTech("Html5");
  if (!Html5) return;

  const mime = /^application\/(x-mpegURL|vnd\.apple\.mpegURL)$/i;
  const supports = (source) => !source.skipContribHlsJs &&
    (mime.test(source.type || "") || /\.m3u8(?:[?#]|$)/i.test(source.src || ""));

  Html5.registerSourceHandler({
    canHandleSource: (source) => supports(source) ? "probably" : "",
    canPlayType: (type) => mime.test(type) ? "probably" : "",
    handleSource(source, tech) {
      const media = tech.el();
      const previous = tech.options_.hlsjsConfig || {};
      const config = {};
      // Legacy defaults include controller classes incompatible with modern HLS.js.
      // Carry over only the playback preferences Channels actually configures.
      for (const key of ["maxBufferLength", "startLevel", "forceKeyFrameOnDiscontinuity",
        "levelLoadingTimeOut", "fragLoadingTimeOut", "manifestLoadingTimeOut"]) {
        if (typeof previous[key] === typeof Hls.DefaultConfig[key] &&
            ["number", "boolean"].includes(typeof previous[key])) config[key] = previous[key];
      }
      const hls = new Hls(config);
      let recoveredAt = -Infinity;
      hls.on(Hls.Events.ERROR, (_, error) => {
        if (!error.fatal) return;
        if (error.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
        else if (error.type === Hls.ErrorTypes.MEDIA_ERROR && performance.now() - recoveredAt > 5000) {
          recoveredAt = performance.now();
          hls.recoverMediaError();
        }
      });
      // Preserve the HLS events consumed by VideoJS plugins and Channels controls.
      for (const event of Object.values(Hls.Events)) {
        hls.on(event, (_, data) => tech.trigger(event, data));
      }
      if (!tech.featuresNativeTextTracks) {
        Object.defineProperty(media, "textTracks", {value: tech.textTracks, writable: false});
        media.addTextTrack = (...args) => tech.addTextTrack(...args);
      }
      hls.attachMedia(media);
      hls.loadSource(source.src);
      return {
        hls,
        duration: () => media.duration || 0,
        dispose: () => hls.destroy(),
      };
    },
  }, 0);
  window.ChannelsPlayerCompatibility = {version: Hls.version};
})();
