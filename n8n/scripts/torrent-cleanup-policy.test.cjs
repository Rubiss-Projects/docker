const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load(file) {
  const filename = path.join(__dirname, file);
  const source = fs.readFileSync(filename, 'utf8').split('\nmain().catch')[0];
  const context = { require, console, process, __filename: filename, __dirname };
  vm.runInNewContext(source, context);
  return context;
}

test('tracker deletion needs fresh confirmation from every tracker of a private torrent', () => {
  const { confirmedDeletion } = load('cleanup_tracker_deleted.js');
  const now = 1000000;
  const tracker = { lastAnnounceTime: now - 60, lastAnnounceSucceeded: false, lastAnnounceResult: 'Torrent has been deleted.' };
  const torrent = { isPrivate: true, error: 2, trackerStats: [tracker] };
  assert.equal(confirmedDeletion(torrent, now), tracker.lastAnnounceResult);
  for (const change of [
    { isPrivate: false }, { error: 3 }, { trackerStats: [] },
    { trackerStats: [{ ...tracker, lastAnnounceTime: now - 86401 }] },
    { trackerStats: [{ ...tracker, lastAnnounceResult: 'Connection timed out' }] },
    { trackerStats: [tracker, { ...tracker, lastAnnounceSucceeded: true }] },
    { trackerStats: [tracker, { lastAnnounceTime: 0 }] },
    { trackerStats: [{ ...tracker, lastScrapeSucceeded: true, lastScrapeTime: now }] },
  ]) assert.equal(confirmedDeletion({ ...torrent, ...change }, now), null);
});

test('failed injections exclude real downloads, completed seeds, and near-complete repairs', () => {
  const { getStuckReason } = load('cleanup_crossseed_stuck.js');
  const torrent = { status: 0, error: 0, percentDone: 0, downloadedEver: 0, uploadedEver: 0, doneDate: 0, downloadDir: '/data/cross-seed-links/test' };
  const args = { maxPercent: 5 };
  assert.equal(getStuckReason(torrent, args), 'stopped-below-threshold');
  for (const change of [
    { downloadedEver: 1 }, { uploadedEver: 1 }, { doneDate: 1 },
    { downloadedEver: undefined }, { status: 4 }, { status: 6 }, { error: 3 },
    { percentDone: 0.999, isStalled: true }, { percentDone: 1 },
    { downloadDir: '/data/downloads/sonarr' },
  ]) assert.equal(getStuckReason({ ...torrent, ...change }, args), null);
});

test('tracker removals always preserve data and recheck eligibility', async () => {
  const context = load('cleanup_tracker_deleted.js');
  const calls = [];
  context.rpcCall = async (_url, _sid, method, args) => {
    calls.push({ method, args });
    return { torrents: [{ id: 1, isPrivate: true, error: 2, trackerStats: [{ lastAnnounceTime: Date.now()/1000 - 1, lastAnnounceSucceeded: false, lastAnnounceResult: 'Torrent has been deleted.' }] }] };
  };
  await context.removeTorrents('test', 'test', [1]);
  assert.equal(calls[1].args['delete-local-data'], false);
  context.rpcCall = async () => ({ torrents: [] });
  await assert.rejects(context.removeTorrents('test', 'test', [1]), /state changed/);
});

test('cross-seed removals recheck history and the configured threshold, preserving media', async () => {
  const context = load('cleanup_crossseed_stuck.js');
  const calls = [];
  let torrent = { id: 1, labels: ['cross-seed'], status: 0, error: 0, percentDone: 0.01, downloadedEver: 0, uploadedEver: 0, doneDate: 0, downloadDir: '/data/cross-seed-links/test' };
  context.rpcCall = async (_url, _sid, method, args) => {
    calls.push({ method, args });
    return { torrents: [torrent] };
  };
  await context.removeTorrents('test', 'test', [1], { maxPercent: 2 });
  assert.equal(calls[1].args['delete-local-data'], false);
  for (const change of [{ percentDone: 0.03 }, { downloadedEver: 1 }, { status: 4 }, { id: 2 }]) {
    const original = torrent;
    torrent = { ...original, ...change };
    calls.length = 0;
    await assert.rejects(context.removeTorrents('test', 'test', [1], { maxPercent: 2 }), /state changed/);
    assert.equal(calls.length, 1);
    torrent = original;
  }
});
