import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const workRoot = join(here, '.work');
mkdirSync(workRoot, { recursive: true });
const work = mkdtempSync(join(workRoot, 'run-'));
console.log(`Evidence: ${work}`);
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, 0, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout.trim();
}

const compiler = join(root, 'tests/stdlib/compiler.sh');
const source = join(here, 'CallbackState.kt');
const cp = run('classpath', 'bash', [compiler, '--classpath']);
const oracle = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', oracle]);
const expected = run('jvm-run', 'java', ['-cp', `${oracle}:${cp}`, 'callbackstate.JvmOracleKt']).split('\n');

const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...[
  'core/Frontend.kt', 'core/Constructors.kt', 'core/ConstructorDispatch.kt', 'core/DefaultArguments.kt',
  'core/OfficialLowerings.kt', 'core/ExpectedNullability.kt', 'core/LibraryInlining.kt', 'core/BinaryBodies.kt',
  'core/LocalDeclarations.kt', 'core/ForLoops.kt', 'core/Contract.kt', 'core/CallCaptures.kt',
  'core/GenericBounds.kt', 'core/SourceSelection.kt', 'core/SourceDiagnostics.kt', 'core/Backend.kt',
  'lower/EtsLoweringPhases.kt', 'lower/EtsBackendContext.kt', 'lower/IrToEts.kt',
  'target/Tree.kt', 'target/Validator.kt', 'target/TypeSubstitution.kt', 'target/Traversal.kt',
  'language/LanguageLowering.kt', 'language/ClassNaming.kt', 'language/OverloadNaming.kt',
  'language/TargetFailures.kt', 'language/TopLevelProperties.kt', 'language/FileInitialization.kt',
  'language/ObjectMembers.kt', 'language/EnumMembers.kt', 'language/InterfaceTypes.kt', 'language/VirtualBridges.kt',
  'language/Varargs.kt', 'stdlib/StandardLibraryRules.kt', 'stdlib/StandardLibraryDependencies.kt',
  'stdlib/StandardLibrarySupport.kt', 'stdlib/ExceptionRules.kt', 'stdlib/ExceptionSupport.kt',
  'stdlib/StringBuilderRule.kt', 'stdlib/MapSetRules.kt', 'stdlib/CollectionEmptinessRules.kt',
  'stdlib/CollectionSupport.kt', 'stdlib/EnumRules.kt', 'stdlib/EqualityRules.kt', 'stdlib/FloatingPointRules.kt',
  'stdlib/IterationRules.kt', 'stdlib/LetRule.kt', 'stdlib/LongValueRule.kt',
].map(path => join(root, 'src', path)), join(here, 'TypedStateProbe.kt'), '-d', probe]);
console.log(run('typed-ir', 'java', ['-cp', `${probe}:${cp}`, 'dev.ets.TypedStateProbeKt', cp, source]));

const output = join(work, 'CallbackState.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, source]);
const code = readFileSync(output, 'utf8');
const compiled = ts.transpileModule(code, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
const inputs = [[0, 1, 2], [3, 1, -2], [-4, 8, -1], [7, -3, 2]];
const actual = inputs.map(args => String(context.exports.callbackState(...args)));
assert.deepEqual(actual, expected);
assert.match(code, /=> \{/);
assert.match(code, /local = local \+ delta/);
assert.match(code, /\.total =/);
assert.match(code, /\.enabled =/);
assert.match(code, /if \(/);
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, expected, actual, output }, null, 2));
console.log('PASS public language pipeline: callback state transitions match the same-input JVM oracle');
