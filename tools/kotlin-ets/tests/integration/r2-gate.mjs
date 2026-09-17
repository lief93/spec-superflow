import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
assert.equal(process.argv.length, 2, 'This is the fixed R2 host queue; SDK/native acceptance is separate');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const files = directory => readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
  if (entry.name.startsWith('.')) return [];
  const path = join(directory, entry.name);
  return entry.isDirectory() ? files(path) : /\.(kt|ets|mjs|py|sh|json)$/.test(entry.name) ? [path] : [];
});
const inputs = [...files(join(root, 'src')), ...files(join(root, 'tests')), join(root, 'kotlin-ets')]
  .sort().map(path => ({ path, sha256: hash(path) }));
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/r2-gate-'));
console.log(`Evidence: ${work}`);
const suites = [
  ['target', 'bash', 'target/run.sh'],
  ['backend', 'bash', 'backend/run.sh'],
  ['adapter-contract', 'bash', 'adapter-contract/run.sh'],
  ['language', 'node', 'language/run.mjs'],
  ['inheritance', 'node', 'inheritance/run.mjs'],
  ['generic-heritage', 'node', 'inheritance/generic/run.mjs'],
  ['generic-methods', 'node', 'inheritance/methods/probe.mjs'],
  ['bounded-receivers', 'node', 'inheritance/bounds/probe.mjs'],
  ['local-functions', 'node', 'local-functions/run.mjs'],
  ['local-captures', 'node', 'local-classes/captures/run.mjs'],
  ['inner-chains', 'node', 'inner-classes/chains/run.mjs'],
  ['constructor-captures', 'node', 'constructors/captures/run.mjs'],
  ['defaults', 'node', 'inheritance/defaults/run.mjs'],
  ['constructors', 'node', 'constructors/run.mjs'],
  ['bridges', 'node', 'inheritance/bridges/run.mjs'],
  ['variance', 'node', 'inheritance/variance/run.mjs'],
  ['composition', 'node', 'inheritance/composition/run.mjs'],
  ['modules', 'node', 'modules/run.mjs'],
  ['cross-file-overloads', 'node', 'modules/overloads/cross-file/run.mjs'],
  ['nested-modules', 'node', 'modules/nested-classes/run.mjs'],
  ['generic-library', 'node', 'stdlib/generic-modules/run.mjs'],
  ['bounded-library', 'node', 'stdlib/bounded-modules/run.mjs'],
  ['method-library', 'node', 'stdlib/generic-methods/run.mjs'],
  ['overload-library', 'node', 'stdlib/overloads/run.mjs'],
  ['inline', 'node', 'inline/run.mjs'],
  ['dependency-ownership', 'node', 'binary-bodies/r1/run.mjs'],
  ['binary-members', 'node', 'binary-bodies/r2e/run.mjs'],
  ['adapter-modules', 'node', 'adapter-modules/run.mjs'],
].map(([name, command, file]) => ({ name, command, args: [join(root, 'tests', file)], state: 'pending' }));
const result = { level: 'R2 fixed language/library/module host regression; not SDK/native or whole-stage acceptance',
  inputs, suites, hostPassed: false, sdkPassed: false, nativePassed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const verifyInputs = () => inputs.forEach(input => assert.equal(hash(input.path), input.sha256, 'Changed during gate: ' + input.path));
record();
for (const [index, suite] of suites.entries()) {
  verifyInputs();
  suite.state = 'running'; suite.startedAt = new Date().toISOString(); record();
  console.log(`[${index + 1}/${suites.length}] ${suite.name}`);
  const observed = spawnSync(suite.command, suite.args, { cwd: root, encoding: 'utf8', timeout: 1800000, maxBuffer: 64 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC', KOTLIN_ETS_BUILD_SLOT: '1' } });
  suite.status = observed.status; suite.error = observed.error?.message;
  suite.finishedAt = new Date().toISOString();
  for (const stream of ['stdout', 'stderr']) {
    const path = join(work, suite.name + '.' + stream); writeFileSync(path, observed[stream] ?? '');
    suite[stream] = { path, sha256: hash(path) };
  }
  suite.evidence = [...(observed.stdout ?? '').matchAll(/^Evidence:\s*(.+)$/gm)].map(match => match[1].trim());
  suite.state = !observed.error && observed.status === 0 ? 'passed' : 'failed'; record();
  assert.equal(suite.state, 'passed', `${suite.name}: ${observed.error?.message ?? ''}\n${observed.stdout}\n${observed.stderr}`);
  console.log(`PASS ${suite.name}`);
}
verifyInputs(); result.hostPassed = true; record();
console.log(`PASS ${suites.length} fixed R2 host suites; SDK/native and documented boundary accounting still required`);
