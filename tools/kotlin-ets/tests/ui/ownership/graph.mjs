import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/graph-'));
console.log(`Evidence: ${work}`);
const files = ['src/target/Tree.kt', 'src/target/Traversal.kt', 'src/ui/BuilderOwnership.kt', 'tests/ui/ownership/OwnershipGraph.kt'].map(p => join(root, p));
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const result = { inputs: files.map(path => ({ path, sha256: hash(path) })), commands: [] };
function run(label, command, args) {
  const value = spawnSync(command, args, { encoding: 'utf8', timeout: 120000, env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status });
  writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
  assert.equal(value.error, undefined);
  assert.equal(value.status, 0, value.stdout + value.stderr);
  return value.stdout.trim();
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']);
const jar = join(work, 'graph.jar');
run('compile', 'bash', [compiler, ...files, '-d', jar]);
console.log(run('graph', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.OwnershipGraphKt']));
for (const input of result.inputs) assert.equal(hash(input.path), input.sha256);
result.passed = true;
writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
