#!/usr/bin/env node
/**
 * Clean up stuck cross-seed torrents from Transmission.
 *
 * Node.js port of cleanup_crossseed_stuck.py for n8n container compatibility.
 * (n8n images no longer include Python or the Alpine apk package manager)
 *
 * Removes torrents injected by cross-seed that failed piece verification. This
 * includes near-0% stopped torrents, plus aged near-complete torrents that stay
 * active or queued because only unmatched files remain.
 *
 * Also cleans up corresponding .torrent files from cross-seed's output directory
 * to prevent re-injection on the next scan cycle.
 *
 * Usage:
 *   node cleanup_crossseed_stuck.js [--dry-run] [--max-percent 5] [--near-complete-percent 99] [--near-complete-max-left-mb 512] [--grace-hours 1]
 *   node cleanup_crossseed_stuck.js --json --rpc-url http://transmission:9091/transmission/rpc/
 */

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const DEFAULT_RPC_URL = 'http://localhost:9091/transmission/rpc/';
const DEFAULT_CROSS_SEED_DIR = path.join(
  path.dirname(path.dirname(path.resolve(__filename))),
  'cross-seed', 'config', 'cross-seeds'
);
const DEFAULT_MAX_PERCENT = 5.0;
const DEFAULT_NEAR_COMPLETE_PERCENT = 99.0;
const DEFAULT_NEAR_COMPLETE_MAX_LEFT_MB = 512;
const DEFAULT_GRACE_HOURS = 1.0;
const DOWNLOAD_STATES = new Set([0, 3, 4]);

function parseArgs() {
  const args = {
    dryRun: false,
    maxPercent: DEFAULT_MAX_PERCENT,
    nearCompletePercent: DEFAULT_NEAR_COMPLETE_PERCENT,
    nearCompleteMaxLeftMb: DEFAULT_NEAR_COMPLETE_MAX_LEFT_MB,
    graceHours: DEFAULT_GRACE_HOURS,
    jsonOutput: false,
    rpcUrl: DEFAULT_RPC_URL,
    crossSeedDir: DEFAULT_CROSS_SEED_DIR,
  };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '--dry-run':
        args.dryRun = true;
        break;
      case '--max-percent':
        args.maxPercent = parseFloat(argv[++i]);
        break;
      case '--near-complete-percent':
        args.nearCompletePercent = parseFloat(argv[++i]);
        break;
      case '--near-complete-max-left-mb':
        args.nearCompleteMaxLeftMb = parseFloat(argv[++i]);
        break;
      case '--grace-hours':
        args.graceHours = parseFloat(argv[++i]);
        break;
      case '--json':
        args.jsonOutput = true;
        break;
      case '--rpc-url':
        args.rpcUrl = argv[++i];
        break;
      case '--cross-seed-dir':
        args.crossSeedDir = argv[++i];
        break;
    }
  }
  return args;
}

function httpRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const client = parsed.protocol === 'https:' ? https : http;
    const req = client.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname + parsed.search,
        method: options.method || 'GET',
        headers: options.headers || {},
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => (body += chunk));
        res.on('end', () =>
          resolve({ statusCode: res.statusCode, headers: res.headers, body })
        );
      }
    );
    req.on('error', reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

async function getSessionId(rpcUrl) {
  const res = await httpRequest(rpcUrl);
  const sid = res.headers['x-transmission-session-id'];
  if (sid) return sid;

  if (res.body && res.body.includes('X-Transmission-Session-Id')) {
    const match = res.body.match(/X-Transmission-Session-Id:\s*([^\s<]+)/);
    if (match) return match[1];
  }

  throw new Error(
    'Failed to get Transmission session ID. Is Transmission running?'
  );
}

async function rpcCall(rpcUrl, sessionId, method, args) {
  const payload = { method };
  if (args) payload.arguments = args;

  const res = await httpRequest(rpcUrl, {
    method: 'POST',
    headers: {
      'X-Transmission-Session-Id': sessionId,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  const result = JSON.parse(res.body);
  if (result.result !== 'success') {
    throw new Error('RPC call failed: ' + JSON.stringify(result));
  }
  return result.arguments || {};
}

function isCrossSeed(torrent) {
  const labels = torrent.labels || [];
  return labels.some((label) => label.toLowerCase().includes('cross-seed'));
}

function getStuckReason(torrent, args) {
  if (!DOWNLOAD_STATES.has(torrent.status)) return null;

  const percent = torrent.percentDone * 100;
  if (torrent.status === 0 && percent <= args.maxPercent) {
    return 'stopped-below-threshold';
  }

  const leftMb = (torrent.leftUntilDone || 0) / 1024 / 1024;
  const hasDownloadRate = (torrent.rateDownload || 0) > 0;
  if (
    percent >= args.nearCompletePercent &&
    leftMb <= args.nearCompleteMaxLeftMb &&
    !hasDownloadRate
  ) {
    return 'near-complete-no-rate';
  }

  return null;
}

async function findStuckTorrents(rpcUrl, sessionId, args, graceSeconds) {
  const fields = [
    'id',
    'name',
    'status',
    'percentDone',
    'leftUntilDone',
    'rateDownload',
    'isStalled',
    'labels',
    'hashString',
    'addedDate',
  ];
  const result = await rpcCall(rpcUrl, sessionId, 'torrent-get', { fields });

  const now = Date.now() / 1000;
  const stuck = [];

  for (const t of result.torrents || []) {
    if (!isCrossSeed(t)) continue;

    const reason = getStuckReason(t, args);
    if (!reason) continue;

    const age = now - (t.addedDate || now);
    if (age < graceSeconds) continue;

    t.cleanupReason = reason;
    stuck.push(t);
  }
  return stuck;
}

async function removeTorrents(rpcUrl, sessionId, ids) {
  await rpcCall(rpcUrl, sessionId, 'torrent-remove', {
    ids,
    'delete-local-data': true,
  });
}

function cleanupTorrentFiles(crossSeedDir, torrents, jsonOutput) {
  if (!fs.existsSync(crossSeedDir)) {
    if (!jsonOutput) {
      console.log('  Warning: cross-seed directory not found: ' + crossSeedDir);
    }
    return 0;
  }

  let removed = 0;
  for (const filename of fs.readdirSync(crossSeedDir)) {
    const lowerName = filename.toLowerCase();
    for (const torrent of torrents) {
      const hash = (torrent.hashString || '').toLowerCase();
      const name = (torrent.name || '').toLowerCase();
      if ((hash && lowerName.includes(hash)) || (name && lowerName.includes(name))) {
        try {
          fs.unlinkSync(path.join(crossSeedDir, filename));
          if (!jsonOutput) console.log('  Removed: ' + filename);
          removed++;
        } catch (e) {
          if (!jsonOutput)
            console.log('  Failed to remove ' + filename + ': ' + e.message);
        }
        break;
      }
    }
  }
  return removed;
}

function buildRemovedList(stuck) {
  const now = Date.now() / 1000;
  return stuck.map((t) => ({
    id: t.id,
    name: t.name,
    percentDone: Math.round(t.percentDone * 1000) / 10,
    leftMiB: Math.round(((t.leftUntilDone || 0) / 1024 / 1024) * 10) / 10,
    status: t.status,
    cleanupReason: t.cleanupReason,
    hashString: t.hashString,
    ageHours: Math.round(((now - (t.addedDate || 0)) / 3600) * 10) / 10,
  }));
}

async function main() {
  const args = parseArgs();
  const graceSeconds = args.graceHours * 3600;

  if (!args.jsonOutput) {
    console.log('Cross-seed stuck torrent cleanup');
    console.log('  Low-percent stopped max:    ' + args.maxPercent + '%');
    console.log('  Near-complete min:          ' + args.nearCompletePercent + '%');
    console.log(
      '  Near-complete max left:     ' + args.nearCompleteMaxLeftMb + ' MiB'
    );
    console.log('  Grace period:               ' + args.graceHours + 'h');
    console.log('  Dry run:                    ' + args.dryRun);
    console.log();
  }

  let sessionId;
  try {
    sessionId = await getSessionId(args.rpcUrl);
  } catch (e) {
    if (args.jsonOutput) {
      console.log(
        JSON.stringify({ error: e.message, removed: [], count: 0 })
      );
      return;
    }
    console.error('Error: ' + e.message);
    process.exit(1);
  }

  const stuck = await findStuckTorrents(
    args.rpcUrl,
    sessionId,
    args,
    graceSeconds
  );

  if (stuck.length === 0) {
    if (args.jsonOutput) {
      console.log(JSON.stringify({ removed: [], count: 0 }));
    } else {
      console.log('No stuck cross-seed torrents found.');
    }
    return;
  }

  const now = Date.now() / 1000;
  if (!args.jsonOutput) {
    console.log('Found ' + stuck.length + ' stuck torrent(s):');
    for (const t of stuck) {
      const ageHours = ((now - (t.addedDate || 0)) / 3600).toFixed(1);
      const pct = (t.percentDone * 100).toFixed(1);
      const leftMb = ((t.leftUntilDone || 0) / 1024 / 1024).toFixed(1);
      console.log(
        '  [' +
          String(t.id).padStart(4) +
          '] ' +
          pct.padStart(5) +
          '% | ' +
          leftMb.padStart(7) +
          ' MiB left | status ' +
          t.status +
          ' | ' +
          ageHours.padStart(6) +
          'h old | ' +
          t.cleanupReason +
          ' | ' +
          t.name
      );
    }
    console.log();
  }

  if (args.dryRun) {
    if (args.jsonOutput) {
      const removedList = buildRemovedList(stuck);
      console.log(
        JSON.stringify({
          removed: removedList,
          count: removedList.length,
          dryRun: true,
        })
      );
    } else {
      console.log('Dry run — no changes made.');
    }
    return;
  }

  const ids = stuck.map((t) => t.id);

  if (!args.jsonOutput) {
    console.log('Removing ' + ids.length + ' torrent(s) from Transmission...');
  }
  await removeTorrents(args.rpcUrl, sessionId, ids);
  if (!args.jsonOutput) console.log('  Done.');

  if (!args.jsonOutput) {
    console.log(
      'Cleaning up .torrent files from cross-seed output directory...'
    );
  }
  const torrentFilesCleaned = cleanupTorrentFiles(
    args.crossSeedDir,
    stuck,
    args.jsonOutput
  );
  if (!args.jsonOutput) {
    console.log('  Cleaned up ' + torrentFilesCleaned + ' .torrent file(s).');
    console.log('\nCleanup complete: ' + ids.length + ' torrent(s) removed.');
  } else {
    const removedList = buildRemovedList(stuck);
    console.log(
      JSON.stringify({
        removed: removedList,
        count: removedList.length,
        torrentFilesCleaned,
      })
    );
  }
}

main().catch((e) => {
  try {
    const args = parseArgs();
    if (args.jsonOutput) {
      console.log(
        JSON.stringify({ error: e.message, removed: [], count: 0 })
      );
      return;
    }
  } catch (_) {
    // ignore parse error in error handler
  }
  console.error('Fatal error: ' + e.message);
  process.exit(1);
});
