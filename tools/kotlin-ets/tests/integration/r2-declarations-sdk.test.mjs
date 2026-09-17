import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
const inputs = readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => {
  const path = join(root, 'src', p);
  return { path, sha256: createHash('sha256').update(readFileSync(path)).digest('hex') };
});
function rejectsBeforeOutput(mutate, message) {
  const work = mkdtempSync(join(tmpdir(), 'r2-evidence-refusal-'));
  try {
    const reports = [65, 90, 70, 160, 30, 3].map(count => ({ passed: true,
      expected: Array(count).fill('oracle'), actual: Array(count).fill('oracle'), moduleActual: Array(count).fill('oracle'),
      inputs: inputs.map(input => ({ ...input })) }));
    mutate(reports);
    const paths = reports.map((report, i) => {
      const path = join(work, String(i)); mkdirSync(path);
      writeFileSync(join(path, 'result.json'), JSON.stringify(report)); return path;
    });
    const result = spawnSync(process.execPath, [join(here, 'r2-declarations-sdk.mjs'), ...paths],
      { encoding: 'utf8', timeout: 10000 });
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    assert.match(result.stderr, message);
    assert.doesNotMatch(result.stdout, /Evidence:/, 'Rejected inputs must not start generation or SDK work');
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
}
test('rejects an unfinished host suite', () => rejectsBeforeOutput(r => { r[0].passed = false; }, /defaults/));
test('rejects missing cases instead of reducing native scope', () => rejectsBeforeOutput(r => {
  r[0].expected.pop();
}, /64 !== 65/));
test('rejects host results that differ from JVM', () => rejectsBeforeOutput(r => {
  r[0].actual[0] = 'wrong';
}, /wrong/));
test('rejects stale compiler evidence', () => rejectsBeforeOutput(r => {
  r[0].inputs[0].sha256 = '0'.repeat(64);
}, /defaults:/));
test('rejects an incomplete production file set', () => rejectsBeforeOutput(r => {
  r[0].inputs.pop();
}, /defaults:/));
