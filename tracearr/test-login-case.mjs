// Run in the pinned image, network none, with this directory read-only at /compat.
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, copyFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { apply, transform } from './patch-login-case.mjs';

const require = createRequire('/app/apps/server/package.json');
const { and, inArray, sql } = require('drizzle-orm');
const { pgTable, text, PgDialect } = require('drizzle-orm/pg-core');
const users = pgTable('users', { username: text('username'), email: text('email'), role: text('role') });
const dialect = new PgDialect();
const originalFile = '/app/apps/server/dist/lib/auth.js';
const original = readFileSync(originalFile, 'utf8');
const patched = transform(original);
assert.equal(transform(patched), patched, 'exact restart output accepted');
assert.throws(() => transform(original + '\nchanged'), /Unsupported/);
assert.throws(() => transform(patched + '\nchanged'), /Unsupported/);

const temporary = mkdtempSync(join(tmpdir(), 'tracearr-auth-compat-'));
try {
  const file = join(temporary, 'auth.js');
  copyFileSync(originalFile, file);
  apply(file);
  apply(file);
  assert.equal(readFileSync(file, 'utf8'), patched);
} finally {
  rmSync(temporary, { recursive: true });
}

// Execute the actual transformed wrapper with recording adapters. No server, DB or credentials.
const start = patched.indexOf('function withLoginScopedUsernameLookup(');
const end = patched.indexOf('\n}', start) + 2;
assert(start >= 0 && end > start);
const staffRoles = ['owner', 'admin'];
const selections = [];
const calls = [];
let matches = [];
let endpoint = '/sign-in/username';
const db = {
  select(fields) {
    return { from(table) {
      assert.equal(table, users);
      return { where(filter) {
        return { async limit(count) {
          assert.equal(count, 2, 'ambiguity must be bounded');
          selections.push({ fields, query: dialect.sqlToQuery(filter) });
          return matches;
        } };
      } };
    } };
  },
};
const factory = new Function('db', 'schema', 'STAFF_ROLES', 'tryGetCurrentAuthEndpointContext',
  'loginAnd', 'loginInArray', 'loginSql', `${patched.slice(start, end)}; return withLoginScopedUsernameLookup;`)(
  db, { users }, staffRoles, () => ({ path: endpoint }), and, inArray, sql);
const adapter = factory(() => ({ findOne(data) { calls.push(data); return { adapterResult: true }; } }))({});
const username = (value, extra = {}) => ({ field: 'username', value, ...extra });

matches = [{ value: 'MixedCase' }];
const input = { model: 'user', where: [username('mixedcase'), { field: 'banned', value: false }], select: ['id'] };
assert.deepEqual(await adapter.findOne(input), { adapterResult: true });
assert.equal(calls.at(-1).where[0].value, 'MixedCase');
assert.deepEqual(calls.at(-1).where[1], input.where[1]);
assert.deepEqual(calls.at(-1).where[2], { field: 'role', operator: 'in', value: staffRoles, connector: 'AND' });
assert.deepEqual(calls.at(-1).select, ['id']);
assert.equal(input.where[0].value, 'mixedcase', 'caller input must not be mutated');
assert.equal(selections.at(-1).fields.value, users.username);
assert.deepEqual(selections.at(-1).query.params, ['owner', 'admin', 'mixedcase']);
assert.match(selections.at(-1).query.sql, /"users"\."role" in/);
assert.match(selections.at(-1).query.sql, /lower\("users"\."username"\) = lower\(\$3\)/);

for (const rows of [[], [{ value: 'MixedCase' }, { value: 'MIXEDCASE' }]]) {
  matches = rows;
  const before = calls.length;
  assert.equal(await adapter.findOne({ model: 'user', where: [username('mixedcase')] }), null);
  assert.equal(calls.length, before, 'missing or ambiguous staff identity must not reach adapter');
}

matches = [{ value: 'Owner@Example.invalid' }];
endpoint = '/sign-in/email';
await adapter.findOne({ model: 'user', where: [{ field: 'email', value: 'owner@example.invalid' }] });
assert.equal(selections.at(-1).fields.value, users.email);
assert.equal(calls.at(-1).where[0].value, 'Owner@Example.invalid');

endpoint = '/oauth2/callback/example';
const oauth = { model: 'user', where: [{ field: 'email', value: 'Member@Example.invalid' }] };
let before = selections.length;
await adapter.findOne(oauth);
assert.equal(selections.length, before, 'OIDC email lookup stays outside password-login patch');
assert.equal(calls.at(-1), oauth);
const scoped = { model: 'user', where: [username('mixedcase'), { field: 'role', value: 'member' }] };
await adapter.findOne(scoped);
assert.equal(calls.at(-1), scoped);
assert.equal(selections.length, before, 'explicit role scope must be retained');
const account = { model: 'account', where: [username('mixedcase')] };
await adapter.findOne(account);
assert.equal(calls.at(-1), account);

await adapter.findOne({ model: 'user', where: [username('mixedcase', { operator: 'contains' })] });
assert.equal(selections.length, before, 'arbitrary operators must not be converted to equality');
assert.equal(calls.at(-1).where[0].operator, 'contains');
assert.equal(calls.at(-1).where.at(-1).field, 'role', 'original role restriction still applies');

matches = [];
const literal = "Mixed_%' OR true --";
await adapter.findOne({ model: 'user', where: [username(literal)] });
const query = selections.at(-1).query;
assert.equal(query.params.at(-1), literal);
assert(!query.sql.includes(literal), 'identifier must remain a bound parameter');
assert(!/\blike\b|\bilike\b/i.test(query.sql), 'wildcard characters must not become patterns');
console.log('PASS: pinned output, tamper refusal, repeat apply, unique staff mapping, ambiguity refusal, role/OAuth/operator scope, parameterized literal identifiers');
