import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/gate-'));
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const inputs = readdirSync(join(root, 'src'), { recursive: true }).filter(name => name.endsWith('.kt'))
  .map(name => { const path = join(root, 'src', name); return { path, sha256: hash(path) }; });
const report = { inputs, results: [], passed: false, review: 'deferred',
  level: 'JVM/ETS host and actual SDK compilation, not native execution' };
const record = () => writeFileSync(join(work, 'report.json'), JSON.stringify(report, null, 2));
const suites = ['computed', 'initialization', 'equality', 'enums', 'types',
  'collections', 'exceptions', 'super', 'defaults', 'numbers', 'models'];
function run(name, command, args) {
  console.log('START ' + name);
  const result = spawnSync(command, args, { cwd: root, encoding: 'utf8',
    timeout: 1200000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, name + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, name + '.stderr'), result.stderr ?? '');
  report.results.push({ name, command, args, status: result.status, error: result.error?.message }); record();
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, (result.stdout + result.stderr).slice(-5000));
  for (const input of inputs) assert.equal(hash(input.path), input.sha256, 'Compiler changed during gate');
  console.log('PASS ' + name);
  return result.stdout;
}
console.log('Gate evidence: ' + work); record();
try {
  run('target', 'bash', [join(root, 'tests/target/run.sh')]);
  let defaultsEvidence;
  for (const suite of suites) {
    const stdout = run(suite, process.execPath, [join(here, '..', suite, 'run.mjs')]);
    if (suite === 'defaults') defaultsEvidence = stdout.match(/^Evidence: (.+)$/m)?.[1];
  }
  run('nullability', process.execPath, [join(root, 'tests/nullability/run.mjs')]);
  run('type-boundaries', process.execPath, [join(here, '../types/rejections.mjs')]);
  assert.ok(defaultsEvidence);
  run('sdk', process.execPath, [join(here, '../defaults/sdk.mjs'), defaultsEvidence]);
  report.passed = true;
} finally { record(); }
console.log('PASS complete main-path spec gate: ' + join(work, 'report.json'));
