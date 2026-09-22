#!/usr/bin/env node
'use strict';

const http = require('http');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const CONTAINER_NAME_PATTERN = /^[a-z0-9][a-z0-9_.-]*$/;
const args = parseArgs(process.argv.slice(2));
const container = (args.container || process.env.CONTAINER_NAME || '').trim().toLowerCase();
const dockerBaseUrl = new URL(process.env.DOCKER_API_URL || 'http://socket-proxy:2375');
const requestTimeoutMs = numberArg(args.requestTimeoutMs, 'REQUEST_TIMEOUT_MS', 15000);
const restartTimeoutSec = numberArg(args.restartTimeoutSeconds, 'RESTART_TIMEOUT_SECONDS', container === 'transmission' ? 60 : 10);
const verifyTimeoutMs = numberArg(args.verifyTimeoutMs, 'VERIFY_TIMEOUT_MS', container === 'transmission' ? 600000 : 90000);
const pollIntervalMs = numberArg(args.pollIntervalMs, 'POLL_INTERVAL_MS', 3000);
const graceMs = numberArg(args.graceMs, 'UNHEALTHY_GRACE_MS', container === 'transmission' ? 180000 : 0, 0);
const cooldownMs = numberArg(args.cooldownMs, 'RECOVERY_COOLDOWN_MS', 900000);
const stateDir = process.env.RECOVERY_STATE_DIR || '/root/.n8n/recovery';
const lockDir = process.env.RECOVERY_LOCK_DIR || '/tmp/container-recovery-locks';
const pendingPath = path.join(stateDir, `${container}.json`);
const pausePath = path.join(stateDir, `${container}.paused`);
const actions = [];
let containerId;
let pending;
let originalStartedAt;

if (!container) {
  fail('Missing --container argument');
}

if (!CONTAINER_NAME_PATTERN.test(container)) {
  fail(`Invalid Docker container name: ${container}`);
}

if (args.locked === 'true') {
  main().catch((error) => fail(error.message, { actions }));
} else {
  // Kernel-held locks survive neither process death nor n8n restarts. Keep the
  // lock on Linux /tmp, not the Windows-backed persistent state directory.
  fs.mkdirSync(lockDir, { recursive: true });
  // BusyBox flock has no -E flag. Lock contention exits 1 without output;
  // the recovery child always emits JSON, and flock setup errors emit stderr.
  const child = spawn('flock', ['-n', path.join(lockDir, `${container}.lock`),
    process.execPath, __filename, ...process.argv.slice(2), '--locked=true'], { stdio: ['inherit', 'pipe', 'pipe'] });
  let hadOutput = false;
  for (const [input, output] of [[child.stdout, process.stdout], [child.stderr, process.stderr]]) {
    input.on('data', (chunk) => {
      hadOutput = true;
      output.write(chunk);
    });
  }
  child.on('error', (error) => fail(error.message));
  child.on('close', (code) => {
    if (code === 1 && !hadOutput) {
      finish({ ok: true, container, actions, result: 'recovery_already_running' });
    }
    process.exit(code ?? 1);
  });
}

async function main() {
  if (fs.existsSync(pausePath)) {
    finish({ ok: true, container, actions, result: 'maintenance_paused' });
  }
  let before = await getContainer();
  containerId = before.Id;
  originalStartedAt = before.State.StartedAt;
  if (!containerId) throw new Error('Docker inspection did not return a container ID');
  fs.mkdirSync(stateDir, { recursive: true });
  pending = fs.existsSync(pendingPath) ? JSON.parse(fs.readFileSync(pendingPath, 'utf8')) : null;
  if (pending && pending.containerId !== containerId) clearPending();
  const beforeStatus = summarize(before);

  if (isRecovered(before) || (isHealthy(before) && pending && Date.now() - pending.attemptedAt >= cooldownMs)) {
    clearPending();
    finish({ ok: true, container, before: beforeStatus, actions, result: 'no_action' });
  }
  if (args.watchdog === 'true' && isStopped(before) && !pending) {
    finish({ ok: true, container, before: beforeStatus, actions, result: 'stopped_without_recovery_intent' });
  }
  if (isStopped(before)) {
    if (pending?.lastStartAt && Date.now() - pending.lastStartAt < cooldownMs) {
      finish({ ok: false, container, before: beforeStatus, actions, result: 'start_cooldown' }, 1);
    }
    actions.push({ action: 'start', reason: `container status is ${before.State.Status}` });
    await startContainer();
  } else if (before.State.Status === 'running' && before.State.Health?.Status === 'unhealthy') {
    if (pending && Date.now() - pending.attemptedAt < cooldownMs) {
      // A timed-out restart can still be stopping the container in Docker.
      actions.push({ action: 'observe_pending_recovery' });
    } else {
      before = await waitForGrace(before);
      if (before.State.Status === 'running' && before.State.Health?.Status === 'unhealthy') {
        await recoverUnhealthy();
      }
    }
  }

  const after = await waitForRecovery();
  const afterStatus = summarize(after);
  const healthyEnough = isRecovered(after);
  if (healthyEnough) clearPending();

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
  if (fs.existsSync(pausePath)) throw new Error('Recovery paused for maintenance');
  if (container === 'transmission') await captureDiagnostics();
  if (fs.existsSync(pausePath)) throw new Error('Recovery paused for maintenance');
  savePending({ attemptedAt: Date.now(), lastStartAt: null, kind: 'restart', startedAt: originalStartedAt });
  actions.push({ action: 'restart', reason: 'container health is unhealthy' });

  try {
    await docker('POST', `/containers/${containerId}/restart?t=${restartTimeoutSec}`, {
      timeoutMs: (restartTimeoutSec * 1000) + 5000,
      ok: [204],
    });
  } catch (error) {
    actions.push({ action: 'restart_failed', message: error.message });
  }
  // Docker already escalates to SIGKILL after restart's grace period. A client
  // timeout does not cancel that operation; an additional kill races its start.
}

async function captureDiagnostics() {
  // Existing Docker read access is sufficient. Never persist Config/Env, mounts,
  // raw daemon logs or tracker URLs. A failed capture must not block recovery.
  try {
    const snapshot = { capturedAt: new Date().toISOString(), containerId };
    const results = await Promise.allSettled([
      docker('GET', `/containers/${containerId}/json`, { timeoutMs: 3000 }),
      docker('GET', `/containers/${containerId}/stats?stream=false&one-shot=true`, { timeoutMs: 3000 }),
    ]);
    const [inspect, stats] = results;
    if (inspect.status === 'fulfilled') {
      const info = inspect.value.json;
      snapshot.state = { ...summarize(info), startedAt: info.State.StartedAt,
        finishedAt: info.State.FinishedAt, oomKilled: info.State.OOMKilled,
        restartCount: info.RestartCount };
      snapshot.health = (info.State.Health?.Log || []).slice(-5).map((entry) => {
        // Only our structured probe output is eligible for persistence.
        let probe;
        try {
          const value = JSON.parse(entry.Output);
          probe = { rpc_up: value.rpc_up, listener_up: value.listener_up,
            rpc_seconds: value.rpc_seconds, observed_at: value.observed_at,
            diagnostics: value.diagnostics };
        } catch { probe = { unavailable: true }; }
        return { start: entry.Start, end: entry.End, exitCode: entry.ExitCode, probe };
      });
    } else snapshot.inspectionUnavailable = true;
    if (stats.status === 'fulfilled') {
      const value = stats.value.json;
      snapshot.resources = { read: value?.read, memory: value?.memory_stats,
        cpu: value?.cpu_stats, blockIO: value?.blkio_stats, pids: value?.pids_stats };
    } else snapshot.statsUnavailable = true;
    const dir = path.join(stateDir, 'diagnostics');
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    const name = `transmission-${Date.now()}.json`;
    const serialized = JSON.stringify(snapshot, null, 2);
    if (Buffer.byteLength(serialized) > 128 * 1024) throw new Error('Diagnostic size limit exceeded');
    fs.writeFileSync(path.join(dir, name), serialized, { mode: 0o600 });
    // Retain the newest 20 incidents, independently of recovery intent.
    const older = fs.readdirSync(dir).filter((file) => /^transmission-\d+\.json$/.test(file)).sort().slice(0, -20);
    for (const file of older) fs.unlinkSync(path.join(dir, file));
    actions.push({ action: 'diagnostics_saved', file: name });
  } catch {
    actions.push({ action: 'diagnostics_unavailable' });
  }
}

async function startContainer() {
  if (fs.existsSync(pausePath)) throw new Error('Recovery paused for maintenance');
  savePending({ attemptedAt: pending?.attemptedAt ?? Date.now(), lastStartAt: Date.now(), kind: 'start' });
  try {
    await docker('POST', `/containers/${containerId}/start`, {
      timeoutMs: requestTimeoutMs,
      ok: [204, 304],
    });
  } catch (error) {
    actions.push({ action: 'start_failed', message: error.message });
  }
}

async function getContainer() {
  const result = await docker('GET', `/containers/${containerId || encodeURIComponent(container)}/json`, {
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
  let deadline = Date.now() + verifyTimeoutMs;
  let last = await getContainer();
  let startedDuringVerification = Boolean(pending?.lastStartAt && Date.now() - pending.lastStartAt < cooldownMs);

  while (Date.now() < deadline) {
    if (fs.existsSync(pausePath)) throw new Error('Recovery paused for maintenance');
    try {
      last = await getContainer();
    } catch (error) {
      actions.push({ action: 'inspection_failed', message: error.message });
      await sleep(pollIntervalMs);
      continue;
    }
    if (last.State.Status !== 'running') {
      if (last.State.Status === 'restarting') {
        await sleep(pollIntervalMs);
        continue;
      }
      if (!['created', 'exited'].includes(last.State.Status)) {
        actions.push({
          action: 'not_startable_during_verification',
          reason: `container entered non-startable status ${last.State.Status}`,
        });
        return last;
      }
      if (args.watchdog === 'true' && !pending) {
        actions.push({ action: 'stopped_without_recovery_intent' });
        return last;
      }
      if (startedDuringVerification) {
        actions.push({
          action: 'stopped_after_verification_start',
          reason: `container became ${last.State.Status} after being started during verification`,
        });
        return last;
      }
      actions.push({
        action: 'start_during_verification',
        reason: `container became ${last.State.Status} during recovery verification`,
      });
      await startContainer();
      startedDuringVerification = true;
      deadline = Date.now() + verifyTimeoutMs;
      await sleep(pollIntervalMs);
      continue;
    }
    if (isRecovered(last)) {
      return last;
    }
    await sleep(pollIntervalMs);
  }

  // Keep pending intent on disk so a later watchdog invocation can finish a
  // shutdown that outlasts this bounded verification window.
  return last;
}

async function waitForGrace(last) {
  const deadline = Date.now() + graceMs;
  while (Date.now() < deadline && last.State.Status === 'running' && last.State.Health?.Status === 'unhealthy') {
    if (fs.existsSync(pausePath)) throw new Error('Recovery paused for maintenance');
    await sleep(pollIntervalMs);
    last = await getContainer();
  }
  return last;
}

function isHealthy(info) {
  return info.State.Status === 'running' && (!info.State.Health || info.State.Health.Status === 'healthy');
}

function isRecovered(info) {
  // A healthy response from the old process does not mean an in-flight Docker
  // restart has completed. Wait for its new start time before clearing intent.
  return isHealthy(info) && (pending?.kind !== 'restart' || info.State.StartedAt !== pending.startedAt);
}

function isStopped(info) {
  return ['created', 'exited'].includes(info.State.Status);
}

function savePending(values) {
  pending = { ...pending, containerId, ...values };
  fs.writeFileSync(`${pendingPath}.tmp`, JSON.stringify(pending));
  fs.renameSync(`${pendingPath}.tmp`, pendingPath);
}

function clearPending() {
  fs.rmSync(pendingPath, { force: true });
  pending = null;
}

function docker(method, path, { timeoutMs, ok = [200, 204] } = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, dockerBaseUrl);
    const req = http.request(url, { method, timeout: timeoutMs }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('error', reject);
      res.on('data', (chunk) => {
        body += chunk;
        if (body.length > 2 * 1024 * 1024) req.destroy(new Error('Docker response exceeded size limit'));
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

    const deadline = setTimeout(() => {
      req.destroy(new Error(`Docker ${method} ${path} exceeded ${timeoutMs}ms`));
    }, timeoutMs);
    req.on('close', () => clearTimeout(deadline));
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

function numberArg(argValue, envName, fallback, minimum = Number.MIN_VALUE) {
  const value = Number(argValue ?? process.env[envName] ?? fallback);
  return Number.isFinite(value) && value >= minimum ? value : fallback;
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
