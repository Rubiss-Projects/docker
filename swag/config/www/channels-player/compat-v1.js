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
      let hasPlayed = false;
      const markPlayed = () => { hasPlayed = true; };
      // A freshly transcoded live stream can begin after timestamp zero. VideoJS
      // may seek to zero before metadata arrives, leaving HLS waiting in that gap.
      const startAtBufferedMedia = () => {
        if (hasPlayed || media.paused || !hls.latestLevelDetails?.live || !media.buffered.length) return;
        const first = media.buffered.start(0);
        if (media.currentTime < first) {
          media.currentTime = Math.min(first + 0.05, media.buffered.end(0));
        }
      };
      media.addEventListener("playing", markPlayed);
      media.addEventListener("play", startAtBufferedMedia);
      hls.on(Hls.Events.FRAG_BUFFERED, startAtBufferedMedia);
      let recoveredAt = -Infinity;
      let recoveries = 0;
      let recoveryTimer;
      hls.on(Hls.Events.ERROR, (_, error) => {
        if (!error.fatal) return;
        if (recoveryTimer !== undefined) return;
        if (++recoveries > 2 || ![Hls.ErrorTypes.NETWORK_ERROR, Hls.ErrorTypes.MEDIA_ERROR].includes(error.type)) {
          hls.stopLoad();
          window.videojs.players[tech.options_.playerId].error({code: error.type === Hls.ErrorTypes.NETWORK_ERROR ? 2 : 3,
            message: "The stream could not recover. Close the player and start playback again."});
          return;
        }
        // A second fatal error still gets recovery; avoid a tight restart loop.
        recoveryTimer = setTimeout(() => {
          recoveryTimer = undefined;
          recoveredAt = performance.now();
          if (error.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
          else {
            // VideoJS otherwise treats HLS reattachment's loadstart as a new
            // source and disposes the handler that is trying to recover.
            tech.off(media, "loadstart", Html5.prototype.firstLoadStartListener_);
            tech.off(media, "loadstart", Html5.prototype.successiveLoadStartListener_);
            tech.one(media, "loadstart", Html5.prototype.firstLoadStartListener_);
            hls.recoverMediaError();
          }
        }, Math.max(0, 5000 - (performance.now() - recoveredAt)));
      });
      // Preserve the HLS events consumed by VideoJS plugins and Channels controls.
      for (const event of Object.values(Hls.Events)) {
        hls.on(event, (_, data) => tech.trigger(event, data));
      }
      const trackDescriptors = {};
      if (!tech.featuresNativeTextTracks) {
        for (const key of ["textTracks", "addTextTrack"]) {
          trackDescriptors[key] = Object.getOwnPropertyDescriptor(media, key);
        }
        Object.defineProperty(media, "textTracks", {value: tech.textTracks(), configurable: true});
        Object.defineProperty(media, "addTextTrack", {
          value: (...args) => tech.addTextTrack(...args), configurable: true,
        });
      }
      hls.attachMedia(media);
      hls.loadSource(source.src);
      return {
        hls,
        duration: () => media.duration || 0,
        dispose() {
          clearTimeout(recoveryTimer);
          media.removeEventListener("playing", markPlayed);
          media.removeEventListener("play", startAtBufferedMedia);
          hls.destroy();
          for (const [key, descriptor] of Object.entries(trackDescriptors)) {
            if (descriptor) Object.defineProperty(media, key, descriptor);
            else delete media[key];
          }
        },
      };
    },
  }, 0);
  window.ChannelsPlayerCompatibility = {version: Hls.version};
})();
