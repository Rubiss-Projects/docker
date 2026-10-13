const assert = require('node:assert/strict');
const { execFile } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { promisify } = require('node:util');
const { test } = require('node:test');

const execute = promisify(execFile);

async function fixture(t, contents) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'irc-watchdog-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const stateFile = path.join(directory, 'state.json');
  const secretsFile = path.join(directory, 'secrets.json');
  if (contents !== undefined) fs.writeFileSync(stateFile, contents);
  fs.writeFileSync(secretsFile, JSON.stringify({ AUTOBRR_RECOVERY_API_KEY: 'test-only' }));
  let restarts = 0;
  const server = http.createServer((request, response) => {
    if (request.url === '/api/irc') {
      response.end(JSON.stringify([{ id: 1, name: 'TestNetwork', enabled: true, connected: false, healthy: false }]));
    } else if (request.url === '/metrics') {
      response.end('autobrr_irc_channel_enabled_total{network="TestNetwork"} 1\nautobrr_irc_channel_monitored_total{network="TestNetwork"} 0\n');
    } else if (request.url === '/api/irc/network/1/restart') {
      restarts++;
      response.writeHead(204).end();
    } else {
      response.writeHead(404).end();
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  return {
    directory, stateFile, restarts: () => restarts,
    run: async (...args) => {
      const { stdout } = await execute(process.execPath, [
        path.join(__dirname, 'autobrr_irc_watchdog.js'), '--state-file', stateFile,
        '--secrets-file', secretsFile, '--api-base', `${base}/api`, '--metrics-url', `${base}/metrics`,
        '--failure-threshold', '1', ...args,
      ]);
      return JSON.parse(stdout);
    },
  };
}

test('zero-filled state is preserved and reset without bypassing cooldown', async (t) => {
  const corrupt = Buffer.alloc(678);
  const f = await fixture(t, corrupt);
  const result = await f.run();
  assert.equal(result.stateRecovery.action, 'reset-corrupt-state');
  assert.deepEqual(fs.readFileSync(result.stateRecovery.backup), corrupt);
  assert.equal(result.networks[0].action, 'cooldown');
  assert.equal(f.restarts(), 0);
  const again = await f.run();
  assert.equal(again.stateRecovery, null);
  assert.equal(again.networks[0].action, 'cooldown');
  assert.equal(f.restarts(), 0);
  const state = JSON.parse(fs.readFileSync(f.stateFile));
  state.networks.TestNetwork.lastRestartAt = new Date(Date.now() - 31 * 60_000).toISOString();
  fs.writeFileSync(f.stateFile, JSON.stringify(state));
  assert.equal((await f.run()).networks[0].action, 'restarted');
  assert.equal(f.restarts(), 1);
});

test('dry run reports corrupt state without modifying files or restarting', async (t) => {
  const f = await fixture(t, '{truncated');
  const before = fs.readdirSync(f.directory);
  const result = await f.run('--dry-run');
  assert.equal(result.stateRecovery.action, 'would-reset-corrupt-state');
  assert.equal(result.stateRecovery.backup, null);
  assert.equal(fs.readFileSync(f.stateFile, 'utf8'), '{truncated');
  assert.deepEqual(fs.readdirSync(f.directory), before);
  assert.equal(f.restarts(), 0);
});

test('invalid state shapes and cooldown timestamps are recovered conservatively', async (t) => {
  for (const state of [null, [], {}, { networks: [] }, { networks: { TestNetwork: { failures: '3', lastRestartAt: null } } }, { networks: { TestNetwork: { failures: 3, lastRestartAt: 'invalid' } } }]) {
    await t.test(JSON.stringify(state), async (t) => {
      const f = await fixture(t, JSON.stringify(state));
      assert.equal((await f.run()).networks[0].action, 'cooldown');
      assert.equal(f.restarts(), 0);
    });
  }
});

test('first run without state uses normal restart admission', async (t) => {
  const f = await fixture(t);
  const result = await f.run();
  assert.equal(result.stateRecovery, null);
  assert.equal(result.networks[0].action, 'restarted');
  assert.equal(f.restarts(), 1);
});
