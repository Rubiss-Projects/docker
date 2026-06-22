#!/usr/bin/env node
/**
 * Clean up torrents whose tracker reports the torrent was deleted.
 *
 * The script checks Transmission torrent-level errors and per-tracker
 * announce/scrape results for permanent deletion messages, then removes the
 * matching torrents from Transmission. Local data is kept by default because
 * these are often completed Sonarr/Radarr items that may still be useful.
 *
 * Usage:
 *   node cleanup_tracker_deleted.js [--dry-run] [--grace-hours 1] [--delete-local-data]
 *   node cleanup_tracker_deleted.js --json --rpc-url http://transmission:9091/transmission/rpc/
 */

const http = require('http');
const https = require('https');

const DEFAULT_RPC_URL = 'http://localhost:9091/transmission/rpc/';
const DEFAULT_GRACE_HOURS = 1.0;
const DELETED_PATTERNS = [
  'torrent has been deleted',
  'torrent deleted',
  'deleted torrent',
  'torrent was deleted',
];

function parseArgs() {
  const args = {
    dryRun: false,
    deleteLocalData: false,
    graceHours: DEFAULT_GRACE_HOURS,
    jsonOutput: false,
    rpcUrl: DEFAULT_RPC_URL,
  };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '--dry-run':
        args.dryRun = true;
        break;
      case '--delete-local-data':
        args.deleteLocalData = true;
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

function findDeletionMatch(messages) {
  for (const message of messages) {
    const normalized = String(message || '').toLowerCase();
    if (!normalized) continue;
    if (DELETED_PATTERNS.some((pattern) => normalized.includes(pattern))) {
      return String(message);
    }
  }
  return null;
}

function getTrackerMessages(torrent) {
  const messages = [];
  if (torrent.errorString) messages.push(torrent.errorString);

  for (const tracker of torrent.trackerStats || []) {
    if (tracker.lastAnnounceResult) messages.push(tracker.lastAnnounceResult);
    if (tracker.lastScrapeResult) messages.push(tracker.lastScrapeResult);
  }
  return messages;
}

async function findDeletedTorrents(rpcUrl, sessionId, graceSeconds) {
  const fields = [
    'id',
    'name',
    'status',
    'percentDone',
    'labels',
    'hashString',
    'addedDate',
    'error',
    'errorString',
    'trackerStats',
  ];
  const result = await rpcCall(rpcUrl, sessionId, 'torrent-get', { fields });

  const now = Date.now() / 1000;
  const deleted = [];
  for (const torrent of result.torrents || []) {
    const age = now - (torrent.addedDate || now);
    if (age < graceSeconds) continue;

    const match = findDeletionMatch(getTrackerMessages(torrent));
    if (!match) continue;

    torrent.cleanupReason = 'tracker-deleted';
    torrent.match = match;
    deleted.push(torrent);
  }
  return deleted;
}

async function removeTorrents(rpcUrl, sessionId, ids, deleteLocalData) {
  await rpcCall(rpcUrl, sessionId, 'torrent-remove', {
    ids,
    'delete-local-data': deleteLocalData,
  });
}

function buildRemovedList(torrents) {
  const now = Date.now() / 1000;
  return torrents.map((torrent) => ({
    id: torrent.id,
    name: torrent.name,
    percentDone: Math.round(torrent.percentDone * 1000) / 10,
    status: torrent.status,
    label: (torrent.labels || []).join(','),
    hashString: torrent.hashString,
    cleanupReason: torrent.cleanupReason,
    match: torrent.match,
    ageHours:
      Math.round(((now - (torrent.addedDate || 0)) / 3600) * 10) / 10,
  }));
}

async function main() {
  const args = parseArgs();
  const graceSeconds = args.graceHours * 3600;

  if (!args.jsonOutput) {
    console.log('Tracker-deleted torrent cleanup');
    console.log('  Grace period:      ' + args.graceHours + 'h');
    console.log('  Delete local data: ' + args.deleteLocalData);
    console.log('  Dry run:           ' + args.dryRun);
    console.log();
  }

  let sessionId;
  try {
    sessionId = await getSessionId(args.rpcUrl);
  } catch (e) {
    if (args.jsonOutput) {
      console.log(JSON.stringify({ error: e.message, removed: [], count: 0 }));
      return;
    }
    console.error('Error: ' + e.message);
    process.exit(1);
  }

  const deleted = await findDeletedTorrents(
    args.rpcUrl,
    sessionId,
    graceSeconds
  );

  if (deleted.length === 0) {
    if (args.jsonOutput) {
      console.log(
        JSON.stringify({ removed: [], count: 0, deleteLocalData: args.deleteLocalData })
      );
    } else {
      console.log('No tracker-deleted torrents found.');
    }
    return;
  }

  const removedList = buildRemovedList(deleted);

  if (!args.jsonOutput) {
    console.log('Found ' + deleted.length + ' torrent(s):');
    for (const torrent of removedList) {
      console.log(
        '  [' +
          String(torrent.id).padStart(4) +
          '] ' +
          String(torrent.percentDone).padStart(5) +
          '% | status ' +
          torrent.status +
          ' | ' +
          torrent.label +
          ' | ' +
          torrent.name
      );
      console.log('       ' + torrent.match);
    }
    console.log();
  }

  if (args.dryRun) {
    if (args.jsonOutput) {
      console.log(
        JSON.stringify({
          removed: removedList,
          count: removedList.length,
          dryRun: true,
          deleteLocalData: args.deleteLocalData,
        })
      );
    } else {
      console.log('Dry run - no changes made.');
    }
    return;
  }

  const ids = deleted.map((torrent) => torrent.id);
  if (!args.jsonOutput) {
    console.log('Removing ' + ids.length + ' torrent(s) from Transmission...');
  }
  await removeTorrents(args.rpcUrl, sessionId, ids, args.deleteLocalData);

  if (args.jsonOutput) {
    console.log(
      JSON.stringify({
        removed: removedList,
        count: removedList.length,
        deleteLocalData: args.deleteLocalData,
      })
    );
  } else {
    console.log('Cleanup complete: ' + ids.length + ' torrent(s) removed.');
  }
}

main().catch((e) => {
  try {
    const args = parseArgs();
    if (args.jsonOutput) {
      console.log(JSON.stringify({ error: e.message, removed: [], count: 0 }));
      return;
    }
  } catch (_) {
    // ignore parse error in error handler
  }
  console.error('Fatal error: ' + e.message);
  process.exit(1);
});
