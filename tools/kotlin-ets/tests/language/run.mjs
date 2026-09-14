import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
function run(label, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8' });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (result.error) throw result.error;
  if (result.status !== expected) {
    process.stderr.write(result.stdout + result.stderr);
    process.exit(result.status || 1);
  }
  process.stdout.write(result.stdout);
  return result;
}
for (const fixture of process.argv.slice(2).length ? process.argv.slice(2) :
  ['LanguageSlice.kt', 'DataSlice.kt', 'ScopeSlice.kt', 'ControlSlice.kt', 'SingletonSlice.kt',
    'UnsupportedConstructor.kt', 'UnsupportedEscape.kt', 'UnsupportedReservedName.kt', 'UnsupportedExternalResult.kt', 'UnsupportedOverload.kt',
    'UnsupportedConcatNumber.kt', 'UnsupportedConcatObject.kt', 'UnsupportedDelegatedProperty.kt']) {
  if (fixture === 'UnsupportedOverload.kt') {
    // Historical filename retained after exact-input public-WddLTc positive proof.
    run('legacy-overload-positive', process.execPath,
      [join(root, 'tests/inheritance/methods/overload-positive.mjs'), 'top']);
    continue;
  }
  const output = join(work, fixture + '.ets');
  const negative = fixture.startsWith('Unsupported');
  const result = run(fixture + '-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, join(here, fixture)], negative ? 2 : 0);
  if (negative) {
    const diagnostic = JSON.parse(result.stdout);
    assert.equal(diagnostic.code, 'UNSUPPORTED');
    const reason = {
      'UnsupportedConstructor.kt': /java.util.Date/,
      'UnsupportedEscape.kt': /Return crosses an expression boundary/,
      'UnsupportedReservedName.kt': /reserved __ets target helpers/,
      'UnsupportedExternalResult.kt': /java.time.Instant.now/,
      'UnsupportedConcatNumber.kt': /Unsupported string concatenation operand.*kotlin.Double/,
      'UnsupportedConcatObject.kt': /Unsupported string concatenation operand.*Opaque/,
      'UnsupportedDelegatedProperty.kt': /Delegated and extension properties are not supported/,
    }[fixture];
    assert.match(diagnostic.message, reason);
    assert.equal(resolve(diagnostic.source.file), join(here, fixture));
    assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
    assert.equal(existsSync(output), false);
    console.log(`PASS ${fixture} rejects with source span and no target`);
    continue;
  }
  run(fixture + '-runtime', process.execPath, [join(here, 'oracle.mjs'), output, fixture]);
}
