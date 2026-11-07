const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const test = require('node:test');
const { admitDatabase } = require('./n8n-startup-admission.cjs');

const held = { schemaVersion: 1, approvedSundayWorkflow: null };
const approved = { schemaVersion: 1, approvedSundayWorkflow: { id: 'sunday', publishedVersionId: 'native-v1', nativeValidationCompleted: true } };

function fixture(workflows, statuses, action) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'n8n-admission-'));
  const file = path.join(directory, 'database.sqlite');
  const db = new DatabaseSync(file);
  db.exec('CREATE TABLE workflow_entity (id TEXT, active INTEGER, activeVersionId TEXT, isArchived INTEGER); CREATE TABLE execution_entity (status TEXT)');
  for (const row of workflows) db.prepare('INSERT INTO workflow_entity VALUES (?, ?, ?, ?)').run(...row);
  for (const status of statuses) db.prepare('INSERT INTO execution_entity VALUES (?)').run(status);
  db.close();
  try { action(file); } finally { fs.unlinkSync(file); fs.rmdirSync(directory); }
}

test('restored active workflows are held before server startup', () => {
  fixture([['legacy', 1, 'windows-v1', 0]], ['success'], file => assert.throws(() => admitDatabase(file, held), /not passed native admission/));
});
test('inactive workflows with terminal history pass without changing bytes', () => {
  fixture([['legacy', 0, null, 0]], ['error', 'success'], file => {
    const before = fs.readFileSync(file);
    assert.equal(admitDatabase(file, held).activeWorkflows, 0);
    assert.deepEqual(fs.readFileSync(file), before);
  });
});
test('only the exact validated Sunday published version is admitted', () => {
  fixture([['sunday', 1, 'native-v1', 0]], [], file => assert.equal(admitDatabase(file, approved).activeWorkflows, 1));
  for (const row of [['sunday', 1, 'windows-v1', 0], ['other', 1, 'native-v1', 0]]) {
    fixture([row], [], file => assert.throws(() => admitDatabase(file, approved)));
  }
});
test('pending and unknown restored executions require reconciliation', () => {
  for (const status of ['new', 'running', 'waiting', 'unknown', null]) {
    fixture([], [status], file => assert.throws(() => admitDatabase(file, held), /execution state/));
  }
});
