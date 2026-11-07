// Opt-in compatibility for Tracearr 3.1.3; saved identifiers and credentials stay intact.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, renameSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const sourceHash = '4f4392f884b90a8fc7a196488f2309de4c60581622d37507a3a508e824ca5011';
export const patchedHash = '288c376e761d7307b68c06f121facaea5f0a187468b81cada246fda46407b7ad';
const sha = (text) => createHash('sha256').update(text).digest('hex');

const lookup = `const findOne = (data) => {
            const byEmailForPassword`;
const guardedLookup = `const findOne = async (data) => {
            const byEmailForPassword`;
const original = `                return adapter.findOne({
                    ...data,
                    where: [
                        ...data.where,
                        { field: 'role', operator: 'in', value: [...STAFF_ROLES], connector: 'AND' },
                    ],
                });`;
const replacement = `                const identifier = data.where.find((w) =>
                    w.field === 'username' || (byEmailForPassword && w.field === 'email'));
                let where = data.where;
                // Better Auth normalizes input; retain the saved display spelling.
                // Only a unique staff identity may supply the stored lookup value.
                if (identifier && typeof identifier.value === 'string' &&
                    (identifier.operator === undefined || identifier.operator === 'eq')) {
                    const column = identifier.field === 'username' ? schema.users.username : schema.users.email;
                    const matches = await db.select({ value: column }).from(schema.users).where(loginAnd(
                        loginInArray(schema.users.role, [...STAFF_ROLES]),
                        loginSql\`lower(\${column}) = lower(\${identifier.value})\`,
                    )).limit(2);
                    if (matches.length !== 1)
                        return null;
                    where = data.where.map((condition) => condition === identifier
                        ? { ...condition, value: matches[0].value }
                        : condition);
                }
                return adapter.findOne({
                    ...data,
                    where: [
                        ...where,
                        { field: 'role', operator: 'in', value: [...STAFF_ROLES], connector: 'AND' },
                    ],
                });`;

export function transform(source) {
  const digest = sha(source);
  if (digest === patchedHash) return source;
  if (digest !== sourceHash) throw new Error('Unsupported Tracearr auth module; review login compatibility before upgrading');
  const anchor = "import { randomUUID } from 'node:crypto';";
  const imports = "\nimport { and as loginAnd, inArray as loginInArray, sql as loginSql } from 'drizzle-orm';";
  let output = source;
  for (const [before, after] of [[anchor, anchor + imports], [lookup, guardedLookup], [original, replacement]]) {
    if (output.split(before).length !== 2) throw new Error('Unexpected Tracearr auth patch anchor');
    output = output.replace(before, after);
  }
  output = '// tracearr-login-case-compat-v1\n' + output;
  if (sha(output) !== patchedHash) throw new Error('Unexpected Tracearr auth patch output');
  return output;
}

export function apply(file = '/app/apps/server/dist/lib/auth.js') {
  const source = readFileSync(file, 'utf8');
  const output = transform(source);
  if (source === output) return;
  const temporary = `${file}.login-case-tmp`;
  writeFileSync(temporary, output, { flag: 'wx', mode: statSync(file).mode & 0o777 });
  renameSync(temporary, file);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  apply();
  console.log('[Tracearr] Login case compatibility verified');
}
