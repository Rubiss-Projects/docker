#!/usr/bin/env node
'use strict';

const http = require('http');

const CONTAINER_NAME_PATTERN = /^[a-z0-9][a-z0-9_.-]*$/;
const args = parseArgs(process.argv.slice(2));
const container = (args.container || process.env.CONTAINER_NAME || '').trim().toLowerCase();
const dockerBaseUrl = new URL(process.env.DOCKER_API_URL || 'http://socket-proxy:2375');
const requestTimeoutMs = numberArg(args.requestTimeoutMs, 'REQUEST_TIMEOUT_MS', 15000);
const restartTimeoutSec = numberArg(args.restartTimeoutSeconds, 'RESTART_TIMEOUT_SECONDS', 10);
const verifyTimeoutMs = numberArg(args.verifyTimeoutMs, 'VERIFY_TIMEOUT_MS', 90000);
const pollIntervalMs = numberArg(args.pollIntervalMs, 'POLL_INTERVAL_MS', 3000);
const actions = [];

if (!container) {
  fail('Missing --container argument');
}

if (!CONTAINER_NAME_PATTERN.test(container)) {
  fail(`Invalid Docker container name: ${container}`);
}

main().catch((error) => {
  fail(error.message, { actions });
});

async function main() {
  const before = await getContainer();
  const beforeStatus = summarize(before);

  if (before.State.Status !== 'running') {
    actions.push({ action: 'start', reason: `container status is ${before.State.Status}` });
    await startContainer();
  } else if (before.State.Health && before.State.Health.Status !== 'healthy') {
    await recoverUnhealthy();
  } else {
    finish({ ok: true, container, before: beforeStatus, actions, after: beforeStatus, result: 'no_action' });
    return;
  }

  const after = await waitForRecovery();
  const afterStatus = summarize(after);
  const healthyEnough = after.State.Status === 'running'
    && (!after.State.Health || after.State.Health.Status === 'healthy');

  finish({
    ok: healthyEnough,
    container,
    before: beforeStatus,
    actions,
    after: afterStatus,
    result: healthyEnough ? 'recovered' : 'not_healthy_after_recovery',
  }, healthyEnough ? 0 : 1);
}

async function recoverUnhealthy() {
  actions.push({ action: 'restart', reason: 'container health is unhealthy' });

  try {
    await docker('POST', `/containers/${encodeURIComponent(container)}/restart?t=${restartTimeoutSec}`, {
      timeoutMs: (restartTimeoutSec * 1000) + 5000,
      ok: [204],
    });
    return;
  } catch (error) {
    actions.push({ action: 'restart_failed', message: error.message });
  }

  let current = await getContainer();
  if (current.State.Status !== 'running') {
    actions.push({ action: 'start_after_failed_restart', reason: `container status is ${current.State.Status}` });
    await startContainer();
    return;
  }

  actions.push({ action: 'force_kill', reason: 'container was still running after restart failed' });
  await docker('POST', `/containers/${encodeURIComponent(container)}/kill?signal=SIGKILL`, {
    timeoutMs: requestTimeoutMs,
    ok: [204, 409],
  });

  await sleep(2000);
  current = await getContainer();
  if (current.State.Status !== 'running') {
    actions.push({ action: 'start_after_force_kill', reason: `container status is ${current.State.Status}` });
    await startContainer();
  }
}

async function startContainer() {
  await docker('POST', `/containers/${encodeURIComponent(container)}/start`, {
    timeoutMs: requestTimeoutMs,
    ok: [204, 304],
  });
}

async function getContainer() {
  const result = await docker('GET', `/containers/${encodeURIComponent(container)}/json`, {
    timeoutMs: requestTimeoutMs,
    ok: null,
  });

  if (result.statusCode === 404) {
    throw new Error(`Container not found: ${container}`);
  }
  if (result.statusCode < 200 || result.statusCode >= 300) {
    throw new Error(`Docker returned HTTP ${result.statusCode} for ${container}: ${result.body}`);
  }

  return result.json;
}

async function waitForRecovery() {
  const deadline = Date.now() + verifyTimeoutMs;
  let last = await getContainer();

  while (Date.now() < deadline) {
    last = await getContainer();
    if (last.State.Status === 'running' && (!last.State.Health || last.State.Health.Status === 'healthy')) {
      return last;
    }
    await sleep(pollIntervalMs);
  }

  return last;
}

function docker(method, path, { timeoutMs, ok = [200, 204] } = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, dockerBaseUrl);
    const req = http.request(url, { method, timeout: timeoutMs }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        let json = null;
        if (body) {
          try {
            json = JSON.parse(body);
          } catch {
            json = null;
          }
        }

        const response = { statusCode: res.statusCode, body: body.trim(), json };
        if (ok === null || ok.includes(res.statusCode)) {
          resolve(response);
          return;
        }

        const message = json && json.message ? json.message : body.trim();
        const error = new Error(`Docker ${method} ${path} returned HTTP ${res.statusCode}${message ? `: ${message}` : ''}`);
        error.response = response;
        reject(error);
      });
    });

    req.on('timeout', () => {
      req.destroy(new Error(`Docker ${method} ${path} timed out after ${timeoutMs}ms`));
    });
    req.on('error', reject);
    req.end();
  });
}

function summarize(info) {
  return {
    status: info.State.Status,
    running: info.State.Running,
    health: info.State.Health ? info.State.Health.Status : null,
    exitCode: info.State.ExitCode,
  };
}

function parseArgs(argv) {
  const parsed = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith('--')) {
      continue;
    }

    const [key, inlineValue] = arg.slice(2).split('=', 2);
    parsed[key] = inlineValue !== undefined ? inlineValue : argv[i + 1];
    if (inlineValue === undefined) {
      i += 1;
    }
  }
  return parsed;
}

function numberArg(argValue, envName, fallback) {
  const value = Number(argValue || process.env[envName] || fallback);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function finish(payload, code = 0) {
  console.log(JSON.stringify(payload, null, 2));
  process.exit(code);
}

function fail(message, extra = {}) {
  console.error(JSON.stringify({ ok: false, container, error: message, ...extra }, null, 2));
  process.exit(1);
}
