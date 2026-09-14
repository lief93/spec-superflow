import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
function run(label, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8' });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, status, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const sources = ['Application.kt', 'LocalInline.kt', 'InlineLibrary.kt'].map(file => join(here, file));
const library = join(work, 'inline-library.jar');
run('library-build', 'bash', [compiler, sources[2], '-d', library]);
const application = join(work, 'application.jar');
run('application-build', 'bash', [compiler, '-classpath', `${cp}:${library}`, sources[0], sources[1], join(here, 'JvmOracle.kt'), '-d', application]);
const expected = run('jvm-runtime', 'java', ['-cp', `${application}:${library}:${cp}`, 'inlinefixture.JvmOracleKt']).trim().split('\n');
assert.deepEqual(expected, ['45:16:11:7:4:BALDE', '129:23:25:14:11:BALDE', '102', '2']);
const hash = file => createHash('sha256').update(readFileSync(file)).digest('hex');
writeFileSync(join(work, 'library-provenance.json'), JSON.stringify({ bodyRoute: 'explicit-source', libraryJar: library,
  librarySha256: hash(library), sources: sources.map(path => ({ path, sha256: hash(path) })) }, null, 2));

const evidence = join(work, 'evidence.jar');
const core = ['Frontend.kt', 'Constructors.kt', 'ConstructorDispatch.kt', 'DefaultArguments.kt', 'OfficialLowerings.kt', 'ExpectedNullability.kt', 'LibraryInlining.kt', 'BinaryBodies.kt', 'LocalDeclarations.kt', 'ForLoops.kt'].map(file => join(root, 'src/core', file)).filter(existsSync);
run('evidence-build', 'bash', [compiler, ...core, join(root, 'src/core/Contract.kt'),
  ...['Tree.kt', 'Validator.kt', 'TypeSubstitution.kt', 'Traversal.kt'].map(file => join(root, 'src/target', file)),
  join(here, 'InlineEvidence.kt'), '-d', evidence]);
console.log(run('inline-evidence', 'java', ['-cp', `${evidence}:${cp}`, 'dev.ets.InlineEvidenceKt', cp, work, ...sources]).trim());

const output = join(work, 'application.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, ...sources]);
const compiled = ts.transpileModule(readFileSync(output, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
});
assert.deepEqual(compiled.diagnostics, []);
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
const actual = [context.exports.inlineSourceScenario(1), context.exports.inlineSourceScenario(8),
  context.exports.crossFileScenario(3), context.exports.crossFileScenario(-2)].map(String);
writeFileSync(join(work, 'runtime.json'), JSON.stringify({ expected, actual }, null, 2));
assert.deepEqual(actual, expected);
console.log('PASS public CLI/JVM: cross-file inline, built library source, named/default arguments, captured and argument effects');

const binaryOutput = join(work, 'binary-only.ets');
const diagnostic = JSON.parse(run('binary-only', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath', `${cp}:${library}`,
  '--out', binaryOutput, join(here, 'BinaryOnly.kt')], 2));
assert.equal(diagnostic.code, 'UNSUPPORTED');
assert.match(diagnostic.message, /inline.*IR body.*inlinelibrary.libraryTransform/i);
assert.equal(diagnostic.source.file, join(here, 'BinaryOnly.kt'));
assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
assert.equal(existsSync(binaryOutput), false);
console.log('PASS binary-only library: unavailable IR body rejects with source span and no target');
