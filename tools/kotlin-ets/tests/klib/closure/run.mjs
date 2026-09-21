import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compiler, harness, identities, root, sources, hash } from '../../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const stdlib = process.env.KOTLIN_JS_STDLIB ?? resolve(root, '../../../artifacts/kotlin-js-official-prototype-20260913/cache/kotlin-stdlib-js-2.1.20.klib');
assert.ok(existsSync(stdlib), 'Provide the pinned Kotlin 2.1.20 JS stdlib KLIB via KOTLIN_JS_STDLIB');
const fixtures = ['Consumer.kt', 'Oracle.kt'];
const implementation = identities([
  ...sources(join(root, 'src')),
  ...fixtures.map(name => join(here, name)),
  join(here, 'Inspect.kt'),
  fileURLToPath(import.meta.url),
  stdlib,
]);
const input = join(work, 'producer');
mkdirSync(input);
for (const name of fixtures) cpSync(join(here, name), join(input, name));
const jvm = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources(input), '-d', jvm]);
const expected = run('jvm-run', 'java', ['-cp', `${cp}:${jvm}`, 'klibclosure.OracleKt']).trim().split('\n');
assert.deepEqual(expected, ['2,4', '2,3,4,5', '1', 'null']);
run('build-consumer', 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.js.K2JSCompiler',
  '-Xir-produce-klib-file', '-ir-output-dir', work, '-ir-output-name', 'consumer',
  '-libraries', stdlib, join(input, 'Consumer.kt')]);
rmSync(input, { recursive: true });
assert.equal(existsSync(input), false);
const klib = join(work, 'consumer.klib');
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'Inspect.kt'), '-d', probe]);
console.log(run('inspect', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.klibtest.InspectKt', work, klib, stdlib]).trim());
const closure = readFileSync(join(work, 'closure.md'), 'utf8');
assert.match(closure, /## filterEven/);
assert.match(closure, /## mapPlusOne/);
assert.match(closure, /## firstOrNullValue/);
assert.match(closure, /filterTo|MISSING_BODY|COMMON_IR_BODY/);
writeFileSync(join(work, 'result.json'), JSON.stringify({
  passed: true,
  expected,
  implementation,
  binaries: identities([klib]),
  officialLoader: 'KlibLoader / loadIr / JsIrLinker',
  limitation: 'Inspection of official linked IR only; not a claim that ETS can lower stdlib collection bodies',
}, null, 2));
console.log(`PASS closure spike JVM oracle ${JSON.stringify(expected)}; IR graph written`);
