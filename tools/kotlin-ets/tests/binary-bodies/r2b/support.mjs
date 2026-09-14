import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

export const here = dirname(fileURLToPath(import.meta.url));
export const root = resolve(here, '../../..');
export const compiler = join(root, 'tests/stdlib/compiler.sh');
export const core = ['Frontend.kt', 'Constructors.kt', 'ConstructorDispatch.kt', 'DefaultArguments.kt', 'LibraryInlining.kt', 'BinaryBodies.kt', 'OfficialLowerings.kt', 'LocalDeclarations.kt',
  'ForLoops.kt', 'ExpectedNullability.kt', 'Contract.kt'].map(name => join(root, 'src/core', name));
export const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
export const identities = paths => paths.map(path => ({ path, sha256: hash(path) }));
export const sources = directory => readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
  ? sources(join(directory, entry.name)) : entry.name.endsWith('.kt') ? [join(directory, entry.name)] : []);
export function harness(parent = join(here, '.work'), prefix = 'run-') {
  process.env.JAVA_TOOL_OPTIONS = '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC';
  process.env.PATH = `/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin:${process.env.PATH}`;
  mkdirSync(parent, { recursive: true });
  const work = mkdtempSync(join(parent, prefix));
  console.log(`Evidence: ${work}`);
  function run(label, command, args, status = 0) {
    const result = spawnSync(command, args, { encoding: 'utf8', timeout: 300000 });
    writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
      stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
    if (result.error) throw result.error;
    assert.equal(result.status, status, `${label}: ${result.stdout}\n${result.stderr}`);
    return result.stdout;
  }
  return { work, run };
}
