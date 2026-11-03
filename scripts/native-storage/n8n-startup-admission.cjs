const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

// Read admission only: workflow changes use the matching n8n CLI, never SQL writes.
function admitDatabase(databasePath, policy) {
  if (!policy || policy.schemaVersion !== 1 || Object.keys(policy).sort().join(',') !== 'approvedSundayWorkflow,schemaVersion') {
    throw new Error('Invalid native workflow policy');
  }
  const approved = policy.approvedSundayWorkflow;
  if (approved !== null && (!approved || typeof approved.id !== 'string' || !approved.id || typeof approved.publishedVersionId !== 'string' || !approved.publishedVersionId || approved.nativeValidationCompleted !== true)) {
    throw new Error('Sunday approval needs its exact validated workflow and published version');
  }
  const db = new DatabaseSync(databasePath, { readOnly: true });
  try {
    db.exec('PRAGMA query_only=ON');
    const workflows = db.prepare('SELECT id, active, activeVersionId, isArchived FROM workflow_entity').all();
    const active = workflows.filter(w => w.active !== 0 || w.activeVersionId !== null);
    for (const workflow of active) {
      if (!approved || workflow.id !== approved.id || workflow.active !== 1 || workflow.activeVersionId !== approved.publishedVersionId || workflow.isArchived !== 0) {
        throw new Error('An active or published workflow has not passed native admission');
      }
    }
    const executions = db.prepare('SELECT status, COUNT(*) AS count FROM execution_entity GROUP BY status').all();
    const terminal = new Set(['success', 'error', 'canceled', 'crashed']);
    if (executions.some(row => !terminal.has(row.status))) {
      throw new Error('Restored pending or unknown execution state requires review');
    }
    return { workflows: workflows.length, activeWorkflows: active.length, pendingExecutions: 0, databaseOpenedReadOnly: true };
  } finally {
    db.close();
  }
}

if (require.main === module) {
  try {
    if (process.argv.length !== 4 || process.argv[2] !== '--policy') throw new Error('Expected --policy FILE');
    const policy = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    const database = path.join(process.env.N8N_USER_FOLDER || '/home/node', '.n8n', 'database.sqlite');
    console.log(JSON.stringify({ nativeN8nAdmission: true, ...admitDatabase(database, policy) }));
  } catch {
    console.error('Native n8n startup held: database, workflows, pending executions or approval policy need review.');
    process.exitCode = 1;
  }
}

module.exports = { admitDatabase };
