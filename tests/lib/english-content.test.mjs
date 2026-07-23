import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');

function filesUnder(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? filesUnder(path) : [path];
  });
}

describe('published workflow language', () => {
  it('keeps skills and templates free of CJK text', () => {
    for (const directory of ['skills', 'templates']) {
      for (const file of filesUnder(join(root, directory))) {
        assert.doesNotMatch(
          readFileSync(file, 'utf-8'),
          /[\u3400-\u9fff]/u,
          relative(root, file),
        );
      }
    }
  });
});
