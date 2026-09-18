// Run inside the pinned Tracearr image with this directory mounted at /compat.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { patches, transform } from './patch-seerr-books.mjs';

const directory = '/app/apps/server/dist/services/requests';
const originals = patches.map((patch) => readFileSync(`${directory}/${patch.file}`, 'utf8'));
for (let i = 0; i < patches.length; i++) {
  const output = transform(originals[i], patches[i]);
  assert.equal(transform(output, patches[i]), output, 'restart must be idempotent');
  assert.throws(() => transform(originals[i] + '\nchanged', patches[i]));
  assert.throws(() => transform(output + '\nchanged', patches[i]));
}
const temporary = `${directory}/seerrClient.compat-test.mjs`;
writeFileSync(temporary, transform(originals[0], patches[0]));
try {
  const { SeerrClient } = await import(temporary);
  const client = new SeerrClient('http://seerr:5055', 'test-key');
  const movie = { id: 1, status: 2, type: 'movie', createdAt: '2026-09-18', updatedAt: '2026-09-18', media: { id: 1, mediaType: 'movie', status: 5 }, requestedBy: { id: 1, displayName: 'test' } };
  let response;
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => structuredClone(response) });
  const page = (results) => ({ pageInfo: { page: 1, pages: 3, results: 201, pageSize: 100 }, results });
  response = page([...Array.from({length: 99}, () => ({type: 'book'})), movie]);
  let parsed = await client.requestsPage(0, 100);
  assert.equal(parsed.rawResultCount, 100);
  assert.equal(parsed.results.length, 1);
  response = page(Array.from({length: 100}, () => ({type: 'book'})));
  parsed = await client.requestsPage(100, 100);
  assert.equal(parsed.rawResultCount, 100);
  assert.equal(parsed.results.length, 0);
  response = page([{type: 'audiobook'}, movie]);
  parsed = await client.requestsPage(200, 100);
  assert.equal(parsed.rawResultCount, 2);
  assert.equal(parsed.results.length, 1);
  for (const bad of [{type: 'unknown'}, null, {...movie, media: null}]) {
    response = page([bad]);
    await assert.rejects(client.requestsPage(0, 100), /Unexpected Seerr response/);
  }
  // Execute the actual patched fetchRows function without loading its database dependencies.
  const sync = transform(originals[1], patches[1]);
  const start = sync.indexOf('async function fetchRows(');
  const end = sync.indexOf('\nasync function lookupTitles(', start);
  assert.ok(start >= 0 && end > start);
  const fetchRows = new Function('PAGE_SIZE', 'CURSOR_SLACK_MS', `${sync.slice(start,end)}; return fetchRows;`)(100, 300000);
  const offsets = [];
  const rows = await fetchRows({requestsPage: async (skip) => {
    offsets.push(skip);
    return {pageInfo: {pages: 3}, rawResultCount: skip === 200 ? 1 : 100, results: skip === 100 ? [] : [movie]};
  }}, 'full', null);
  assert.deepEqual(offsets, [0,100,200]);
  assert.equal(rows.length, 2);
  console.log('PASS: hashes, repeat startup, mixed/all-book pagination, unknown-type validation, movie validation');
} finally {
  unlinkSync(temporary);
}
