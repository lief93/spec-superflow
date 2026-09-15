import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/rejections-'));
for (const [name, message] of [['Char', 'Char boxing'], ['Number', 'boxed scalar discrimination']]) {
  const out = join(work, `${name}.ets`);
  const result = spawnSync('bash', [resolve(here, '../../../kotlin-ets'), '--mode', 'language', '--out', out,
    join(here, `Unsupported${name}.kt`)], { encoding: 'utf8', timeout: 600000 });
  writeFileSync(join(work, `${name}.stdout`), result.stdout ?? '');
  writeFileSync(join(work, `${name}.stderr`), result.stderr ?? '');
  assert.equal(result.status, 2);
  const diagnostic = JSON.parse(result.stdout.trim());
  assert.match(diagnostic.message, new RegExp(message));
  assert.equal(diagnostic.source.line, 3);
  assert.ok(diagnostic.source.column > 0);
  assert.equal(existsSync(out), false);
}
console.log(`PASS source-linked scalar representation refusals: ${work}`);
