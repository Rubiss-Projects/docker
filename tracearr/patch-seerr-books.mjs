// Compatibility for the Seerr books fork; remove when Tracearr supports it upstream.
// Only the verified Tracearr 2.4.0 modules are accepted. Image updates must review this patch.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const sha = (text) => createHash('sha256').update(text).digest('hex');
const marker = '// tracearr-seerr-books-compat-v1\n';
export const patches = [
  {
    file: 'seerrClient.js',
    hash: 'a40c01cb3d3a063d2426307b2fe6658928355d576dc54a386a174ca0bccb7c63',
    replacements: [
      ['    results: z.array(seerrRequestSchema),', '    results: z.array(seerrRequestSchema),\n    rawResultCount: z.number().int().nonnegative().optional(),'],
      ['        const json = await response.json();', `        const json = await response.json();
        // Books are not modeled by Tracearr. Preserve the upstream page length so
        // an all-book or mixed page cannot terminate the movie/TV sync early.
        if (path.startsWith('/request?') && Array.isArray(json?.results)) {
            json.rawResultCount = json.results.length;
            json.results = json.results.filter((row) =>
                row?.type !== 'book' && row?.type !== 'audiobook');
        }`],
    ],
  },
  {
    file: 'sync.js',
    hash: 'd7bb79f80ea80e82047c3c9f40f1c01a5615ee84ca749b198bf0dbe16c7448e4',
    replacements: [
      ['result.results.length < PAGE_SIZE', '(result.rawResultCount ?? result.results.length) < PAGE_SIZE'],
    ],
  },
];

export function transform(source, patch) {
  if (source.startsWith(marker)) {
    // Validate the exact original by reversing every replacement; do not trust a marker alone.
    let original = source.slice(marker.length);
    for (const [before, after] of [...patch.replacements].reverse()) {
      if (original.split(after).length !== 2) throw new Error(`Invalid patched anchor: ${patch.file}`);
      original = original.replace(after, before);
    }
    if (sha(original) !== patch.hash) throw new Error(`Changed patched module: ${patch.file}`);
    return source;
  }
  if (sha(source) !== patch.hash) throw new Error(`Unsupported upstream module: ${patch.file}; review the Seerr books compatibility patch before upgrading`);
  let result = source;
  for (const [before, after] of patch.replacements) {
    if (result.split(before).length !== 2) throw new Error(`Unexpected upstream anchor: ${patch.file}`);
    result = result.replace(before, after);
  }
  return marker + result;
}

export function apply(directory) {
  // Validate both modules before changing either one. Restarts accept only our exact output.
  const outputs = patches.map((patch) => {
    const path = join(directory, patch.file);
    const source = readFileSync(path, 'utf8');
    return { path, source, result: transform(source, patch) };
  });
  for (const { path, source, result } of outputs) {
    if (source === result) continue;
    writeFileSync(`${path}.compat-tmp`, result);
    renameSync(`${path}.compat-tmp`, path);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  apply('/app/apps/server/dist/services/requests');
  console.log('[Tracearr] Seerr books compatibility verified');
}
