#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const http = require('node:http');
const path = require('node:path');
const test = require('node:test');

const script = path.join(__dirname, 'self_heal_container.js');

test('starts a container that exits after the force-kill wait', async () => {
  const scenario = createScenario({ afterStart: state('running', 'healthy') });

  const result = await runScenario(scenario);

  assert.equal(result.code, 0, result.stderr);
  assert.equal(result.payload.result, 'recovered');
  assert.equal(scenario.actions.filter((action) => action === 'start').length, 1);
  assert.ok(result.payload.actions.some((action) => action.action === 'start_during_verification'));
});

test('does not repeatedly start a container that exits again', async () => {
  const scenario = createScenario({ afterStart: state('exited', 'unhealthy', 137) });

  const result = await runScenario(scenario);

  assert.equal(result.code, 1);
  assert.equal(result.payload.result, 'not_healthy_after_recovery');
  assert.equal(scenario.actions.filter((action) => action === 'start').length, 1);
  assert.equal(
    result.payload.actions.filter((action) => action.action === 'start_during_verification').length,
    1,
  );
  assert.ok(result.payload.actions.some((action) => action.action === 'stopped_after_verification_start'));
});

test('waits through Docker restarting state before starting an exited container', async () => {
  const scenario = createScenario({
    afterStart: state('running', 'healthy'),
    restartingBeforeExit: 2,
  });

  const result = await runScenario(scenario);

  assert.equal(result.code, 0, result.stderr);
  assert.equal(result.payload.result, 'recovered');
  assert.equal(scenario.actions.filter((action) => action === 'start').length, 1);
});

function createScenario({ afterStart, restartingBeforeExit = 0 }) {
  const actions = [];
  let killed = false;
  let started = false;
  let getsAfterKill = 0;
  const server = http.createServer((request, response) => {
    response.setHeader('Content-Type', 'application/json');
    if (request.method === 'GET') {
      let current = state('running', 'unhealthy');
      if (started) {
        current = afterStart;
      } else if (killed) {
        getsAfterKill += 1;
        if (getsAfterKill > 2) {
          if (restartingBeforeExit > 0) {
            restartingBeforeExit -= 1;
            current = state('restarting', 'unhealthy');
          } else {
            current = state('exited', 'unhealthy', 137);
          }
        }
      }
      response.end(JSON.stringify({ State: current }));
      return;
    }

    if (request.url.includes('/restart')) {
      actions.push('restart');
      response.statusCode = 500;
      response.end(JSON.stringify({ message: 'simulated stuck restart' }));
      return;
    }

    if (request.url.includes('/kill')) {
      actions.push('kill');
      killed = true;
      response.statusCode = 204;
      response.end();
      return;
    }

    if (request.url.includes('/start')) {
      actions.push('start');
      started = true;
      response.statusCode = 204;
      response.end();
      return;
    }

    response.statusCode = 404;
    response.end();
  });

  return { actions, server };
}

function state(status, health, exitCode = 0) {
  return {
    Status: status,
    Running: status === 'running',
    ExitCode: exitCode,
    Health: { Status: health },
  };
}

async function runScenario(scenario) {
  await new Promise((resolve) => scenario.server.listen(0, '127.0.0.1', resolve));
  const { port } = scenario.server.address();

  try {
    const child = spawn(process.execPath, [
      script,
      '--container', 'transmission',
      '--requestTimeoutMs', '100',
      '--restartTimeoutSeconds', '0.01',
      '--verifyTimeoutMs', '500',
      '--pollIntervalMs', '30',
      '--postKillWaitMs', '20',
    ], {
      env: { ...process.env, DOCKER_API_URL: `http://127.0.0.1:${port}` },
    });

    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });

    const code = await new Promise((resolve) => child.on('close', resolve));
    const output = stdout || stderr;
    return { code, stderr, payload: JSON.parse(output) };
  } finally {
    await new Promise((resolve) => scenario.server.close(resolve));
  }
}
