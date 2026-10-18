// Compatibility for the Seerr books fork; remove when Tracearr supports it upstream.
// Only reviewed modules through Tracearr 2.8.3 are accepted. Image updates must review this patch.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const sha = (text) => createHash('sha256').update(text).digest('hex');
const marker = '// tracearr-seerr-books-compat-v1\n';
export const patches = [
  {
    file: 'seerrClient.js',
    hashes: ['b97dcc33edbd15729aa5cb295adb4eb2c1ac2e27237248fcf5df8429fea71ed7'],
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
    hashes: [
      '577a716f72a0225be63d4aefbc9095d5ce9a7ce77c30389321be1c9b226ae519',
      // 2.8.3 records the Seerr version during sync; fetchRows is unchanged.
      '873982bc2705340fe66601c179a73a6696ed57d655d37eac6b424c1b1c3bddf3',
    ],
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
    if (!patch.hashes.includes(sha(original))) throw new Error(`Changed patched module: ${patch.file}`);
    return source;
  }
  if (!patch.hashes.includes(sha(source))) throw new Error(`Unsupported upstream module: ${patch.file}; review the Seerr books compatibility patch before upgrading`);
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
