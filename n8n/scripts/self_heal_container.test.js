#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { performance } = require('node:perf_hooks');
const test = require('node:test');
const script = path.join(__dirname, 'self_heal_container.js');

function state(status, health = 'unhealthy', startedAt = 'old') {
  return { Id: 'container-1', State: { Status: status, Running: status === 'running',
    ExitCode: status === 'exited' ? 137 : 0, StartedAt: startedAt, Health: { Status: health } } };
}

async function scenario(t, handler) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'self-heal-test-'));
  const actions = [];
  let current = state('running');
  const server = http.createServer((request, response) => {
    if (request.url.includes('/stats?')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ memory_stats: { usage: 123 }, cpu_stats: {} }));
      return;
    }
    const action = request.method === 'GET' ? 'inspect' : request.url.split('/').at(-1).split('?')[0];
    actions.push(action);
    response.setHeader('Content-Type', 'application/json');
    if (handler?.({ action, request, response, actions, set: (value) => { current = value; } })) return;
    if (action === 'inspect') response.end(JSON.stringify(current));
    else if (action === 'start') {
      current = state('running', 'healthy', 'new');
      response.writeHead(204).end();
    } else response.writeHead(500).end(JSON.stringify({ message: 'restart did not complete' }));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(dir, { recursive: true, force: true });
  });
  const pendingPath = path.join(dir, 'transmission.json');
  const cooldownPath = path.join(dir, 'transmission.cooldown.json');
  function run(extra = []) {
    const child = spawn(process.execPath, [script, '--container', 'transmission',
      '--requestTimeoutMs=1000', '--restartTimeoutSeconds=0.01', '--verifyTimeoutMs=500',
      '--pollIntervalMs=15', '--graceMs=0', '--healthyWindowMs=50', ...extra], {
      env: { ...process.env, DOCKER_API_URL: `http://127.0.0.1:${server.address().port}`,
        RECOVERY_STATE_DIR: dir, RECOVERY_LOCK_DIR: path.join(dir, 'locks'),
        RECOVERY_DIAGNOSTICS_DIR: path.join(dir, 'diagnostics') },
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (data) => { stdout += data; });
    child.stderr.on('data', (data) => { stderr += data; });
    return new Promise((resolve, reject) => {
      child.on('error', reject);
      child.on('close', (code) => {
        try { resolve({ code, payload: JSON.parse(stdout || stderr) }); }
        catch (error) { reject(new Error(`${error.message}: ${stdout} ${stderr}`)); }
      });
    });
  }
  return { run, actions, pendingPath, cooldownPath, dir, set: (value) => { current = value; } };
}

test('healthy recovery preserves the cooldown across flaps until its original expiry', async (t) => {
  const s = await scenario(t, ({ action, response, set }) => {
    if (action === 'restart') {
      set(state('running', 'healthy', 'new'));
      response.writeHead(204).end();
      return true;
    }
  });
  assert.equal((await s.run()).payload.result, 'recovered');
  assert.ok(!fs.existsSync(s.pendingPath));
  const cooldown = fs.readFileSync(s.cooldownPath, 'utf8');
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'no_action');
  s.set(state('running', 'unhealthy', 'new'));
  assert.equal((await s.run()).payload.result, 'not_healthy_after_recovery');
  assert.equal(s.actions.filter((a) => a === 'restart').length, 1);
  assert.equal(fs.readFileSync(s.cooldownPath, 'utf8'), cooldown);

  const expired = JSON.parse(cooldown);
  expired.attemptedAt = Date.now() - 900001;
  fs.writeFileSync(s.cooldownPath, JSON.stringify(expired));
  // A further restart must produce another lifecycle before it can pass.
  s.set(state('running', 'unhealthy', 'old'));
  assert.equal((await s.run()).payload.result, 'recovered');
  assert.equal(s.actions.filter((a) => a === 'restart').length, 2);
});

test('upgrades existing pending intent without renewing or losing its cooldown', async (t) => {
  const s = await scenario(t);
  const attemptedAt = Date.now() - 30000;
  fs.writeFileSync(s.pendingPath, JSON.stringify({ containerId: 'container-1', attemptedAt,
    kind: 'restart', startedAt: 'old' }));
  s.set(state('running', 'healthy', 'new'));
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'recovered');
  assert.ok(!fs.existsSync(s.pendingPath));
  assert.deepEqual(JSON.parse(fs.readFileSync(s.cooldownPath)), { containerId: 'container-1', attemptedAt });
  assert.ok(s.actions.every((a) => a === 'inspect'));
});

test('unfinished recovery uses only its intent and a failed intent write creates no cooldown', async (t) => {
  const pending = await scenario(t);
  assert.equal((await pending.run()).code, 1);
  assert.ok(fs.existsSync(pending.pendingPath));
  assert.ok(!fs.existsSync(pending.cooldownPath));
  const failedWrite = await scenario(t);
  fs.mkdirSync(`${failedWrite.pendingPath}.tmp`);
  const result = await failedWrite.run();
  assert.equal(result.code, 1);
  assert.ok(!failedWrite.actions.includes('restart'));
  assert.ok(!fs.existsSync(failedWrite.cooldownPath));
});

test('cooldown observation releases the lock at expiry without another full verification window', async (t) => {
  for (const unfinished of [false, true]) {
    const s = await scenario(t);
    const receipt = { containerId: 'container-1', attemptedAt: Date.now(), kind: 'restart', startedAt: 'old' };
    fs.writeFileSync(unfinished ? s.pendingPath : s.cooldownPath, JSON.stringify(receipt));
    const began = performance.now();
    const result = await s.run(['--cooldownMs=700', '--verifyTimeoutMs=3000']);
    const elapsed = performance.now() - began;
    assert.equal(result.code, 1);
    assert.ok(result.payload.actions.some((a) => a.action === 'observe_recovery_cooldown'));
    assert.ok(elapsed < 2200, `cooldown observation held the lock for ${elapsed}ms`);
    assert.ok(s.actions.every((a) => a === 'inspect'));
  }
});

test('completed cooldown neither authorizes a watchdog start nor applies to a replacement', async (t) => {
  const s = await scenario(t);
  s.set(state('exited'));
  assert.equal((await s.run()).payload.result, 'recovered');
  s.set(state('exited'));
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'stopped_without_recovery_intent');
  assert.equal((await s.run()).payload.result, 'start_cooldown');
  assert.equal(s.actions.filter((a) => a === 'start').length, 1);
  // This unrelated old ID must not rate-limit an explicitly requested new start.
  fs.writeFileSync(s.cooldownPath, JSON.stringify({ containerId: 'replaced-container', attemptedAt: Date.now() }));
  assert.equal((await s.run()).payload.result, 'recovered');
  assert.equal(s.actions.filter((a) => a === 'start').length, 2);
});

test('a brief healthy observation does not complete recovery or discard intent', async (t) => {
  const s = await scenario(t, ({ action, set }) => {
    if (action === 'restart') set(state('running', 'healthy', 'new'));
  });
  const result = await s.run(['--verifyTimeoutMs=80', '--healthyWindowMs=200']);
  assert.equal(result.code, 1);
  assert.equal(result.payload.after.health, 'healthy');
  assert.equal(result.payload.result, 'not_healthy_after_recovery');
  assert.ok(fs.existsSync(s.pendingPath));
});

test('a relapse after natural recovery releases the lock for the next unhealthy admission', async (t) => {
  let inspections = 0;
  let restarted = false;
  const s = await scenario(t, ({ action, response, set }) => {
    if (action === 'inspect' && !restarted) {
      const n = ++inspections;
      set(state('running', n === 2 || n === 3 ? 'healthy' : 'unhealthy'));
    }
    if (action === 'restart') {
      restarted = true;
      set(state('running', 'healthy', 'new'));
      response.writeHead(204).end();
      return true;
    }
  });
  const began = performance.now();
  const result = await s.run(['--graceMs=200', '--verifyTimeoutMs=3000', '--healthyWindowMs=500']);
  assert.equal(result.code, 1);
  assert.ok(result.payload.actions.some((a) => a.action === 'unhealthy_without_pending_recovery'));
  assert.ok(performance.now() - began < 2200);
  assert.ok(!fs.existsSync(s.pendingPath));
  assert.ok(s.actions.every((a) => a === 'inspect'));
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'recovered');
  assert.equal(s.actions.filter((a) => a === 'restart').length, 1);
});

test('an inspection crossing expiry can finish a late stop but cannot pass late health', async (t) => {
  for (const stopped of [true, false]) {
    let restartRequested = false;
    let delayed = false;
    const s = await scenario(t, ({ action, response, set }) => {
      if (action === 'restart') restartRequested = true;
      if (action === 'inspect' && restartRequested && !delayed) {
        delayed = true;
        const info = stopped ? state('exited') : state('running', 'healthy', 'new');
        setTimeout(() => { set(info); response.end(JSON.stringify(info)); }, 230);
        return true;
      }
    });
    const result = await s.run(['--verifyTimeoutMs=160', '--healthyWindowMs=0']);
    assert.equal(result.code, stopped ? 0 : 1, JSON.stringify(result.payload));
    assert.equal(s.actions.filter((a) => a === 'start').length, stopped ? 1 : 0);
    assert.equal(fs.existsSync(s.pendingPath), !stopped);
  }
});

test('failed checks, unknown inspections and lifecycle changes reset the healthy interval', async (t) => {
  for (const interruption of ['unhealthy', 'failed-check', 'inspection-error', 'lifecycle']) {
    await t.test(interruption, async (t) => {
      let observing = false;
      let healthyInspections = 0;
      const s = await scenario(t, ({ action, response, set }) => {
        if (action === 'restart') { observing = true; set(state('running', 'healthy', 'new')); }
        if (action === 'inspect' && observing) {
          const n = ++healthyInspections;
          // No healthy streak can exceed two polls, even if Docker still calls
          // it healthy while its failing streak has not reached the retry limit.
          const info = state('running', 'healthy', interruption === 'lifecycle' ? `start-${Math.floor(n / 3)}` : 'new');
          if (n % 3 === 0) {
            if (interruption === 'unhealthy') info.State.Health.Status = 'unhealthy';
            if (interruption === 'failed-check') info.State.Health.FailingStreak = 1;
            if (interruption === 'inspection-error') { response.writeHead(500).end('{}'); return true; }
          }
          set(info);
        }
      });
      const result = await s.run(['--verifyTimeoutMs=160', '--healthyWindowMs=70']);
      assert.equal(result.code, 1, JSON.stringify(result.payload));
      assert.ok(fs.existsSync(s.pendingPath));
      assert.ok(!result.payload.actions.some((a) => a.action === 'stable_health'));
    });
  }
});

test('starts a container that exits late after restart fails, without a competing kill', async (t) => {
  let restarted = false;
  let inspections = 0;
  const s = await scenario(t, ({ action, set }) => {
    if (action === 'restart') restarted = true;
    if (action === 'inspect' && restarted && ++inspections === 5) set(state('exited'));
  });
  const result = await s.run();
  assert.equal(result.code, 0, JSON.stringify(result.payload));
  assert.equal(result.payload.result, 'recovered');
  assert.equal(s.actions.filter((a) => a === 'start').length, 1);
  assert.ok(!s.actions.includes('kill'));
  assert.ok(!fs.existsSync(s.pendingPath));
  const diagnosticFiles = fs.readdirSync(path.join(s.dir, 'diagnostics'));
  assert.equal(diagnosticFiles.length, 1);
  const diagnostic = JSON.parse(fs.readFileSync(path.join(s.dir, 'diagnostics', diagnosticFiles[0])));
  assert.equal(diagnostic.state.health, 'unhealthy');
  assert.equal(diagnostic.resources.memory.usage, 123);
  assert.ok(!('Config' in diagnostic));
  assert.deepEqual(result.payload.actions.find((a) => a.action === 'diagnostics_saved').snapshot, diagnostic);
});

test('watchdog finishes shutdown after the original recovery process has exited', async (t) => {
  const s = await scenario(t);
  assert.equal((await s.run()).code, 1);
  assert.ok(fs.existsSync(s.pendingPath));
  s.set(state('exited'));
  const second = await s.run(['--watchdog=true']);
  assert.equal(second.code, 0);
  assert.equal(second.payload.result, 'recovered');
  assert.equal(s.actions.filter((a) => a === 'restart').length, 1);
  assert.equal(s.actions.filter((a) => a === 'start').length, 1);
});

test('watchdog does not start an intentionally stopped or replacement container', async (t) => {
  const s = await scenario(t);
  s.set(state('exited'));
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'stopped_without_recovery_intent');
  fs.writeFileSync(s.pendingPath, JSON.stringify({ containerId: 'replaced-container', attemptedAt: Date.now() }));
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'stopped_without_recovery_intent');
  assert.ok(!s.actions.includes('start'));
});

test('does not restart a transient disk stall that recovers during grace', async (t) => {
  const s = await scenario(t, ({ action, actions, set }) => {
    if (action === 'inspect' && actions.length === 3) set(state('running', 'healthy'));
  });
  assert.equal((await s.run(['--graceMs=200'])).code, 0);
  assert.ok(s.actions.every((a) => a === 'inspect'));
});

test('does not kill starting, restarting, or paused containers', async (t) => {
  const s = await scenario(t);
  for (const value of [state('running', 'starting'), state('restarting'), state('paused')]) {
    s.set(value);
    assert.equal((await s.run(['--watchdog=true'])).code, 1);
  }
  assert.ok(s.actions.every((a) => a === 'inspect'));
});

test('does not start a crash-looping container repeatedly across watchdog executions', async (t) => {
  const s = await scenario(t, ({ action, response }) => {
    if (action === 'start') { response.writeHead(204).end(); return true; }
  });
  s.set(state('exited'));
  assert.equal((await s.run()).code, 1);
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'start_cooldown');
  assert.equal(s.actions.filter((a) => a === 'start').length, 1);
});

test('serializes webhook and watchdog recovery and releases the lock after exit', async (t) => {
  const s = await scenario(t);
  const first = s.run(['--verifyTimeoutMs=500']);
  while (!s.actions.includes('restart')) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'recovery_already_running');
  await first;
  s.set(state('exited'));
  assert.equal((await s.run(['--watchdog=true'])).code, 0);
  assert.equal(s.actions.filter((a) => a === 'restart').length, 1);
});

test('maintenance pause suppresses both webhook and watchdog actions', async (t) => {
  const s = await scenario(t);
  fs.writeFileSync(path.join(s.dir, 'transmission.paused'), '');
  assert.equal((await s.run()).payload.result, 'maintenance_paused');
  assert.equal((await s.run(['--watchdog=true'])).payload.result, 'maintenance_paused');
  assert.deepEqual(s.actions, []);
});

test('does not mistake the old healthy process for completion of an in-flight restart', async (t) => {
  const s = await scenario(t, ({ action, set }) => {
    if (action === 'restart') set(state('running', 'healthy', 'old'));
  });
  assert.equal((await s.run()).code, 1);
  assert.ok(fs.existsSync(s.pendingPath));
  s.set(state('exited'));
  assert.equal((await s.run(['--watchdog=true'])).code, 0);
});

test('bounds a stalled start request and preserves intent for a later attempt', async (t) => {
  const s = await scenario(t, ({ action }) => action === 'start');
  s.set(state('exited'));
  const result = await s.run();
  assert.equal(result.code, 1);
  assert.ok(result.payload.actions.some((a) => a.action === 'start_failed'));
  assert.ok(fs.existsSync(s.pendingPath));
});
