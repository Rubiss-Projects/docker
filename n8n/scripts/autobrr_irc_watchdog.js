#!/usr/bin/env node

/**
 * Deterministic autobrr IRC watchdog.
 *
 * Policy:
 * - Observe enabled networks through the autobrr API and Prometheus metrics.
 * - Require N consecutive unhealthy checks before restarting one network.
 * - Restart at most once per network during the cooldown.
 * - Never modify IRC credentials or perform NickServ account operations.
 */

const fs = require('node:fs');
const path = require('node:path');

function option(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index === -1 ? fallback : process.argv[index + 1];
}

const config = {
  apiBase: option('api-base', process.env.AUTOBRR_API_BASE || 'http://autobrr:7474/api'),
  metricsUrl: option('metrics-url', process.env.AUTOBRR_METRICS_URL || 'http://autobrr:9074/metrics'),
  secretsFile: option('secrets-file', process.env.AUTOBRR_IRC_SECRETS_FILE || '/mnt/e/Docker/n8n/irc-recovery-secrets.json'),
  stateFile: option('state-file', process.env.AUTOBRR_IRC_STATE_FILE || '/mnt/e/Docker/autobrr/config/.irc-watchdog-state.json'),
  failureThreshold: Number(option('failure-threshold', process.env.AUTOBRR_IRC_FAILURE_THRESHOLD || 3)),
  cooldownMinutes: Number(option('cooldown-minutes', process.env.AUTOBRR_IRC_COOLDOWN_MINUTES || 30)),
  dryRun: process.argv.includes('--dry-run'),
};

function readSecret(file, key) {
  const values = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!values || Array.isArray(values) || typeof values !== 'object' || typeof values[key] !== 'string' || !values[key]) {
    throw new Error(`${key} is missing or empty in ${file}`);
  }
  return values[key];
}

function loadState() {
  try {
    const value = JSON.parse(fs.readFileSync(config.stateFile, 'utf8'));
    return value && typeof value === 'object' ? value : { networks: {} };
  } catch (error) {
    if (error.code === 'ENOENT') return { networks: {} };
    throw new Error(`Cannot read watchdog state: ${error.message}`);
  }
}

function saveState(state) {
  if (config.dryRun) return;
  fs.mkdirSync(path.dirname(config.stateFile), { recursive: true });
  const temporary = `${config.stateFile}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporary, config.stateFile);
}

function metricByNetwork(metrics, metricName) {
  const result = new Map();
  const escapedName = metricName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`^${escapedName}\\{network="((?:[^"\\\\]|\\\\.)+)"\\}\\s+(\\d+(?:\\.\\d+)?)$`, 'gm');
  for (const match of metrics.matchAll(pattern)) result.set(match[1].replaceAll('\\"', '"'), Number(match[2]));
  return result;
}

async function request(url, apiKey, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { 'X-API-Token': apiKey, ...(options.headers || {}) },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}`);
  return response;
}

async function main() {
  if (!Number.isInteger(config.failureThreshold) || config.failureThreshold < 1) throw new Error('failure-threshold must be a positive integer');
  if (!Number.isFinite(config.cooldownMinutes) || config.cooldownMinutes < 1) throw new Error('cooldown-minutes must be positive');

  const apiKey = readSecret(config.secretsFile, 'AUTOBRR_RECOVERY_API_KEY');
  const [networksResponse, metricsResponse] = await Promise.all([
    request(`${config.apiBase}/irc`, apiKey),
    fetch(config.metricsUrl, { signal: AbortSignal.timeout(15_000) }),
  ]);
  if (!metricsResponse.ok) throw new Error(`GET ${config.metricsUrl} returned HTTP ${metricsResponse.status}`);

  const networks = await networksResponse.json();
  const metrics = await metricsResponse.text();
  const monitored = metricByNetwork(metrics, 'autobrr_irc_channel_monitored_total');
  const enabledChannels = metricByNetwork(metrics, 'autobrr_irc_channel_enabled_total');
  const state = loadState();
  state.networks ||= {};
  const now = Date.now();
  const cooldownMs = config.cooldownMinutes * 60_000;
  const results = [];

  for (const network of networks.filter((item) => item.enabled)) {
    const channelCount = monitored.get(network.name);
    const enabledChannelCount = enabledChannels.get(network.name);
    const healthy = network.connected === true && network.healthy === true && enabledChannelCount > 0 && channelCount >= enabledChannelCount;
    const previous = state.networks[network.name] || { failures: 0, lastRestartAt: null };
    const current = { ...previous, failures: healthy ? 0 : previous.failures + 1, lastCheckedAt: new Date(now).toISOString() };
    let action = healthy ? 'none' : 'waiting';

    if (!healthy && current.failures >= config.failureThreshold) {
      const lastRestart = current.lastRestartAt ? Date.parse(current.lastRestartAt) : 0;
      if (lastRestart && now - lastRestart < cooldownMs) {
        action = 'cooldown';
      } else {
        action = config.dryRun ? 'restart-dry-run' : 'restarted';
        if (!config.dryRun) await request(`${config.apiBase}/irc/network/${network.id}/restart`, apiKey);
        current.lastRestartAt = new Date(now).toISOString();
        current.failures = 0;
      }
    }

    state.networks[network.name] = current;
    results.push({
      id: network.id,
      name: network.name,
      healthy,
      connected: network.connected === true,
      apiHealthy: network.healthy === true,
      monitoredChannels: channelCount ?? 0,
      enabledChannels: enabledChannelCount ?? 0,
      failures: current.failures,
      action,
    });
  }

  for (const name of Object.keys(state.networks)) {
    if (!networks.some((network) => network.enabled && network.name === name)) delete state.networks[name];
  }
  saveState(state);

  const events = results.filter((item) => !item.healthy || item.action !== 'none');
  process.stdout.write(`${JSON.stringify({ ok: true, checkedAt: new Date(now).toISOString(), dryRun: config.dryRun, events, networks: results })}\n`);
}

main().catch((error) => {
  process.stdout.write(`${JSON.stringify({ ok: false, error: error.message })}\n`);
  process.exitCode = 1;
});
