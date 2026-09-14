import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/probe-'));
console.log(`Evidence: ${work}`);
const files = ['target/Tree.kt', 'target/TypeSubstitution.kt', 'target/Traversal.kt', 'target/Validator.kt',
  'core/Contract.kt', 'language/LanguageLowering.kt', 'language/OverloadNaming.kt', 'stdlib/StandardLibraryRules.kt', 'stdlib/IterationRules.kt',
  'stdlib/StandardLibrarySupport.kt']
  .map(path => join(root, 'src', path)).concat(join(here, 'InheritanceProbe.kt'));
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const inputs = [...files, join(here, 'Inheritance.kt')].map(path => ({ path, sha256: hash(path) }));
writeFileSync(join(work, 'inputs.json'), JSON.stringify(inputs, null, 2));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args) {
  const result = spawnSync(command, args, { env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, JAVA_TOOL_OPTIONS: env.JAVA_TOOL_OPTIONS }, null, 2));
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout.trim();
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']);
const jar = join(work, 'probe.jar');
run('compile', 'bash', [compiler, ...files, '-d', jar]);
console.log(run('test', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.InheritanceProbeKt', join(here, 'Inheritance.kt'), cp, work]));
for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
