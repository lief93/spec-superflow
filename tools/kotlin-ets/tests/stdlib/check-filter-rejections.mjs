import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { assertRuntimeHelpers, ts } from './runtime-assertions.mjs';

const tests = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(tests, '../..');
mkdirSync(path.join(tests, '.build'), { recursive: true });
const run = mkdtempSync(path.join(tests, '.build/filter-rejections.'));
console.log(`Filter rejection evidence: ${run}`);
const rejected = ['Array', 'IntArray', 'String', 'Collection', 'Predicate', 'NonLocal'];
const sources = rejected.map(name => path.join(tests, 'fixtures/filter-rejected', `${name}.kt`));
const valid = spawnSync('bash', [path.join(tests, 'compiler.sh'), '-d', path.join(run, 'valid-kotlin.jar'),
  ...sources], { encoding: 'utf8', timeout: 180000 });
writeFileSync(path.join(run, 'jvm.stderr'), valid.stderr ?? '');
assert.equal(valid.status, 0, 'All rejection fixtures must be valid Kotlin: ' + valid.stderr);
for (const [index, name] of [...rejected, 'FilterShadow'].entries()) {
  const output = path.join(run, `${name}.ets`);
  const fixture = sources[index] ?? path.join(tests, 'fixtures/FilterShadow.kt');
  const cli = spawnSync(path.join(root, 'kotlin-ets'), ['--mode', 'language', '--out', output, fixture],
    { encoding: 'utf8', timeout: 180000 });
  writeFileSync(path.join(run, `${name}.stdout`), cli.stdout ?? '');
  writeFileSync(path.join(run, `${name}.stderr`), cli.stderr ?? '');
  writeFileSync(path.join(run, `${name}.json`), JSON.stringify({ status: cli.status, signal: cli.signal,
    fixture, output, error: cli.error?.message }) + '\n');
  if (name === 'FilterShadow') {
    assert.equal(cli.status, 0, cli.stderr + cli.stdout);
    const text = assertRuntimeHelpers(output, ['__etsListGet']);
    const context = { exports: {} };
    vm.runInNewContext(ts.transpileModule(text, { compilerOptions: {
      target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
    } }).outputText, context);
    assert.equal(context.exports.shadowFilter(), 77);
    assert.equal(context.exports.shadowFilterNot(), 88);
  } else {
    assert.equal(cli.status, 2, cli.stderr + cli.stdout);
    const diagnostic = JSON.parse(cli.stdout);
    assert.equal(diagnostic.ok, false);
    assert.equal(diagnostic.code, 'UNSUPPORTED');
    assert.equal(diagnostic.source.file, fixture);
    assert.ok(diagnostic.source.start >= 0);
    assert.ok(diagnostic.source.end > diagnostic.source.start);
    assert.match(diagnostic.message, name === 'NonLocal' ? /[Rr]eturn|filter/ : /kotlin\.(collections|text)\.filter/);
    assert.ok(!existsSync(output), 'Rejected input must not publish output');
    assert.ok(readFileSync(fixture, 'utf8').length > diagnostic.source.start);
  }
  console.log(`PASS: ${name}`);
}
writeFileSync(path.join(run, 'result.json'), JSON.stringify({ passed: true, rejected: rejected.length,
  shadowedSourceCalls: 2 }) + '\n');
