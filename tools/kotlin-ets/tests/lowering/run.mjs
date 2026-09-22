import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
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
function run(label, command, args, options = {}) {
  const { expectedStatus = 0, ...spawnOptions } = options;
  const result = spawnSync(command, args, { encoding: 'utf8', ...spawnOptions });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, expectedStatus, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const classpath = run('classpath', 'bash', [compiler, '--classpath']).trim();
const fixture = join(here, 'Concatenation.kt');
const scopeFixture = join(root, 'tests/language/ScopeSlice.kt');
const jvmJar = join(work, 'oracle.jar');
run('jvm-compile', 'bash', [compiler, fixture, scopeFixture, join(here, 'JvmOracle.kt'), '-d', jvmJar]);
const expected = run('jvm-runtime', 'java', ['-cp', `${jvmJar}:${classpath}`, 'loweringfixture.JvmOracleKt']).trim().split('\n');
assert.deepEqual(expected, ['nullA8|B9:AB', 'nullA-1|B0:AB', 'start:X11/Y12:XY', 'decimal=1.0:null',
  'item=seen2|changed13|seen13;count=14;events=T2>M3>T13>',
  'item=seen-3|changed8|seen8;count=9;events=T-3>M-2>T8>', '10']);

const output = join(work, 'concatenation.ets');
const agentClasses = join(work, 'agent-classes');
mkdirSync(agentClasses);
run('agent-compile', 'javac', ['--release', '17', '-cp', classpath, '-d', agentClasses, join(here, 'CliSeamAgent.java')]);
const agentManifest = join(work, 'agent.mf');
writeFileSync(agentManifest, 'Premain-Class: CliSeamAgent\n\n');
const agent = join(work, 'cli-seam-agent.jar');
run('agent-jar', 'jar', ['cfm', agent, agentManifest, '-C', agentClasses, '.']);
const traceEnv = { ...process.env,
  JAVA_TOOL_OPTIONS: [process.env.JAVA_TOOL_OPTIONS, `"-javaagent:${agent}"`].filter(Boolean).join(' ') };
function readTrace(label) {
  const trace = JSON.parse(readFileSync(join(work, `${label}.json`), 'utf8')).stderr.split('\n')
    .filter(line => line.startsWith('ETS_SEAM ')).map(line => line.slice('ETS_SEAM '.length));
  writeFileSync(join(work, `${label}-seam.json`), JSON.stringify(trace, null, 2) + '\n');
  return trace;
}
function compileThroughSeam(label, args, fileCount, emitter) {
  run(label, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', ...args], { env: traceEnv });
  const trace = readTrace(label);
  assert.deepEqual(trace.filter(event => !/^Ets(Program|Validator|Printer)\./.test(event)), [
    'EtsLoweringPhases.run:enter', 'EtsLoweringPhases.run:exit',
    'IrToEts.program:enter', 'IrModuleToEts.lower:enter',
    ...Array.from({ length: fileCount }, () => ['IrFileToEts.lower:enter', 'IrFileToEts.lower:exit']).flat(),
    'IrModuleToEts.lower:exit', 'IrToEts.program:exit',
    `ModulesKt.${emitter}:enter`, `ModulesKt.${emitter}:exit`,
  ], 'each output mode must use the same IR-to-typed-program boundary exactly once');
  const boundary = trace.slice(trace.indexOf('IrModuleToEts.lower:exit'), trace.indexOf('IrToEts.program:exit'));
  assert.ok(boundary.includes('EtsProgram.<init>:exit'), 'IrToEts must construct EtsProgram before emission');
  assert.deepEqual(boundary.filter(event => event.startsWith('EtsValidator.')),
    ['EtsValidator.validate:enter', 'EtsValidator.validate:exit'], 'the boundary must validate its typed result before returning');
  assert.ok(boundary.indexOf('EtsProgram.<init>:exit') < boundary.indexOf('EtsValidator.validate:enter'));
  const emission = trace.slice(trace.indexOf(`ModulesKt.${emitter}:enter`), trace.indexOf(`ModulesKt.${emitter}:exit`) + 1);
  const firstPrinter = emission.findIndex(event => event.startsWith('EtsPrinter.') && event.endsWith(':enter'));
  assert.ok(firstPrinter > emission.indexOf('EtsValidator.validate:exit'),
    'the shared emitter must validate the typed program before printing');
  console.log(`PASS ${label}: shared typed boundary, ${fileCount} files, validation before ${emitter}`);
}
compileThroughSeam('public-cli', ['--out', output, fixture], 1, 'emitEtsProgram');
function loadTarget(path) {
  const compiled = ts.transpileModule(readFileSync(path, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const context = { exports: {} };
  vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
  return context.exports;
}
function concatenationResults(target) {
  return [target.orderedConcatenation(7), target.orderedConcatenation(-2),
    target.renamedConcatenation(10), target.foldedConstants(),
    target.stringifyBeforeMutation(2), target.stringifyBeforeMutation(-3)];
}
const source = readFileSync(output, 'utf8');
const actual = concatenationResults(loadTarget(output));
writeFileSync(join(work, 'runtime.json'), JSON.stringify({ expected: expected.slice(0, 6), actual }, null, 2));
assert.deepEqual(actual, expected.slice(0, 6));
assert.match(source, /orderedConcatenation\(initialValue: number\)/);
assert.match(source, /renamedConcatenation\(startingValue: number\)/);
console.log('PASS public CLI / same-input JVM: nullable concatenation, constant formatting, ordered effects and preserved names');
console.log('PASS side-effectful toString: conversion before mutation, conversion after mutation, exact counts and event order');

const modules = join(work, 'modules');
compileThroughSeam('public-cli-modules', ['--out-dir', modules, fixture, scopeFixture], 2, 'emitEtsModules');
assert.deepEqual(readdirSync(modules).sort(), ['Concatenation.ets', 'ScopeSlice.ets']);
const moduleActual = [...concatenationResults(loadTarget(join(modules, 'Concatenation.ets'))),
  String(loadTarget(join(modules, 'ScopeSlice.ets')).scopeSlice())];
writeFileSync(join(work, 'module-runtime.json'), JSON.stringify({ expected, actual: moduleActual }, null, 2));
assert.deepEqual(moduleActual, expected);
console.log('PASS --out-dir: seven same-input JVM/ETS pairs across two source files');

const unsupported = join(root, 'tests/language/UnsupportedExternalResult.kt');
const rejectedOutput = join(work, 'unsupported.ets');
const rejected = JSON.parse(run('public-cli-unsupported', 'bash', [join(root, 'kotlin-ets'),
  '--mode', 'language', '--out', rejectedOutput, unsupported], { env: traceEnv, expectedStatus: 2 }));
assert.equal(rejected.ok, false);
assert.equal(rejected.code, 'UNSUPPORTED');
assert.match(rejected.message, /java.time.Instant.now/);
assert.equal(resolve(rejected.source.file), unsupported);
assert.ok(rejected.source.start >= 0 && rejected.source.end > rejected.source.start);
assert.equal(existsSync(rejectedOutput), false, 'unsupported input must not publish a target');
assert.deepEqual(readTrace('public-cli-unsupported'), [
  'EtsLoweringPhases.run:enter', 'EtsLoweringPhases.run:exit',
  'IrToEts.program:enter', 'IrModuleToEts.lower:enter', 'IrFileToEts.lower:enter',
], 'unsupported input must fail inside the same boundary without returning a program or entering an emitter');
console.log('PASS unsupported external call: source-linked diagnostic, no program, no emission/fallback');

const evidenceJar = join(work, 'ir-evidence.jar');
run('ir-compile', 'bash', [compiler, ...['core/Frontend.kt', 'core/Constructors.kt', 'core/ConstructorDispatch.kt', 'core/DefaultArguments.kt', 'core/OfficialLowerings.kt', 'core/ExpectedNullability.kt', 'core/LibraryInlining.kt', 'core/BinaryBodies.kt', 'core/LocalDeclarations.kt', 'core/ForLoops.kt',
  'core/Contract.kt', 'core/CallCaptures.kt', 'core/GenericBounds.kt', 'core/SourceSelection.kt', 'core/SourceDiagnostics.kt', 'lower/EtsLoweringPhases.kt', 'lower/EtsBackendContext.kt', 'target/Tree.kt', 'target/Validator.kt', 'target/TypeSubstitution.kt', 'target/Traversal.kt'].map(file => join(root, 'src', file)),
  join(here, 'IrEvidence.kt'), '-d', evidenceJar]);
console.log(run('ir-evidence', 'java', ['-cp', `${evidenceJar}:${classpath}`, 'dev.ets.IrEvidenceKt', fixture, classpath, work]).trim());
