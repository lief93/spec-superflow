import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const fixture = join(here, 'signature');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-color-scheme-signature-'));
console.log(`Evidence: ${work}`);

function execute(label, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result;
}

for (const test of [
  { name: 'unknown', factory: 'UnknownFactory.kt', source: 'Unknown.kt', message: /futureRole/ },
  { name: 'invalid', factory: 'InvalidFactory.kt', source: 'Invalid.kt', message: /primary must resolve to Color/ },
]) {
  const dependency = join(work, `${test.name}.jar`);
  execute(`${test.name}-dependency`, 'bash', [join(root, 'tests/stdlib/compiler.sh'),
    join(fixture, 'Color.kt'), join(fixture, 'ColorScheme.kt'), join(fixture, test.factory), '-d', dependency]);
  const classpath = join(work, `${test.name}-classpath.txt`);
  writeFileSync(classpath, dependency + '\n');
  const output = join(work, `${test.name}.ets`);
  const result = execute(test.name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
    '--classpath-file', classpath, '--out', output, join(fixture, test.source)], 2);
  const diagnostic = JSON.parse(result.stdout);
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.match(diagnostic.message, test.message);
  assert.ok(diagnostic.source.file.endsWith(test.source));
  assert.ok(diagnostic.source.line > 0 && diagnostic.source.column > 0);
}

console.log('PASS unknown ColorScheme roles and non-Color role types fail with source locations');
