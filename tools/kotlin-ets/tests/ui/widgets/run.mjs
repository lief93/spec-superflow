import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { compiler, harness, identities, root, sources, hash } from '../../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const stdlib = cp.split(':').find(path => path.endsWith('/kotlin-stdlib-2.1.20.jar'));
const annotations = cp.split(':').find(path => path.endsWith('/annotations-13.0.jar'));
const uiClasspathFile = join(process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06', 'classpath.json');
const uiCp = JSON.parse(readFileSync(uiClasspathFile, 'utf8')).join(':');
const modelSources = sources(join(root, 'src/ui/widgets'));
const backendSources = sources(join(root, 'src/ui/harmony'));
const adapter = join(root, 'src/ui/compose/ComposeWidgetAdapter.kt');
const pipeline = join(root, 'src/ui/pipeline/ComposeWidgetPipeline.kt');
const pipelineProbe = join(here, 'CoreProfilePipelineProbe.kt');
const fixtures = ['Page.kt', 'Unsupported.kt', 'ImageR.java', 'widget_logo.svg',
  'BackendTest.kt', 'WidgetProbe.kt', 'CoreProfile.kt', 'CoreProfilePipelineProbe.kt',
  'StateProfile.kt', 'UnsupportedState.kt', 'StateJvmOracle.kt', 'StatePipelineProbe.kt',
  'InputStateProfile.kt', 'InputStateUnsupported.kt', 'InputStateJvmOracle.kt', 'InputStatePipelineProbe.kt',
  'input-state-sdk.mjs', 'PipelineSeamAgent.java'].map(name => join(here, name));
const implementation = identities([...sources(join(root, 'src')), ...fixtures, fileURLToPath(import.meta.url), uiClasspathFile]);
for (const path of modelSources) assert.doesNotMatch(readFileSync(path, 'utf8'), /import |\bEts[A-Z]|IrCall|androidx|harmony|arkui/);
for (const path of backendSources) assert.doesNotMatch(readFileSync(path, 'utf8'), /org\.jetbrains|androidx|IrCall|ComposeWidget|ArkUiCalls/);
assert.doesNotMatch(readFileSync(adapter, 'utf8'), /Harmony|ArkUi|EtsUiElement|EtsUiAttribute|arkui:|"Stack"|"alignItems"|"fontColor"|"backgroundColor"/);
assert.doesNotMatch(readFileSync(pipeline, 'utf8'), /UiTextModule|ComposeLowering|PageText|TextModule/);
assert.doesNotMatch(readFileSync(pipelineProbe, 'utf8'), /\bEtsProgram\s*\(|\bWidget\s*[.(]|\bChildren\s*\(/);
function compile(name, inputs, classpath) {
  const jar = join(work, `${name}.jar`);
  run(`compile-${name}`, 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
    '-no-stdlib', '-no-reflect', '-classpath', classpath, ...inputs, '-d', jar]);
  return jar;
}
const modelJar = compile('model', modelSources, stdlib);
const targetJar = compile('target', sources(join(root, 'src/target')), `${stdlib}:${annotations}`);
const backendJar = compile('harmony', [...backendSources, join(here, 'BackendTest.kt')], `${stdlib}:${modelJar}:${targetJar}`);
console.log(run('backend-isolation', 'java', ['-cp', [stdlib, modelJar, targetJar, backendJar].join(':'), 'dev.ets.widgettest.BackendTestKt']).trim());
// Adapter and compiler build without any Harmony implementation on their classpath.
const compilerSources = sources(join(root, 'src')).filter(path =>
  !modelSources.includes(path) && !backendSources.includes(path) && path !== adapter && path !== pipeline);
const compilerJar = compile('compiler', compilerSources, cp);
const adapterJar = compile('adapter', [adapter], `${cp}:${modelJar}:${compilerJar}`);
const pipelineJar = compile('pipeline', [pipeline], [cp, modelJar, compilerJar, backendJar, adapterJar].join(':'));
const probeJar = join(work, 'probe.jar');
run('compile-probe', 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-no-stdlib', '-no-reflect',
  '-classpath', [cp, modelJar, compilerJar, backendJar, adapterJar].join(':'), `-Xfriend-paths=${compilerJar}`,
  join(here, 'WidgetProbe.kt'), '-d', probeJar]);
console.log(run('resolved-structure', 'java', ['-cp', [cp, modelJar, compilerJar, backendJar, adapterJar, probeJar].join(':'),
  'dev.ets.widgettest.WidgetProbeKt', uiCp, join(work, 'output'), join(here, 'widget_logo.svg'),
  join(here, 'Page.kt'), join(here, 'Unsupported.kt'), join(here, 'ImageR.java')]).trim());
const pipelineProbeJar = compile('pipeline-probe', [pipelineProbe],
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar].join(':'));
const agentClasses = join(work, 'agent-classes');
mkdirSync(agentClasses);
run('agent-compile', 'javac', ['--release', '17', '-cp', cp, '-d', agentClasses, join(here, 'PipelineSeamAgent.java')]);
const agentManifest = join(work, 'agent.mf');
writeFileSync(agentManifest, 'Premain-Class: PipelineSeamAgent\n\n');
const agentJar = join(work, 'pipeline-seam-agent.jar');
run('agent-jar', 'jar', ['cfm', agentJar, agentManifest, '-C', agentClasses, '.']);
const savedJavaOptions = process.env.JAVA_TOOL_OPTIONS;
process.env.JAVA_TOOL_OPTIONS = `${savedJavaOptions} -javaagent:${agentJar}`;
console.log(run('core-profile-pipeline', 'java', ['-cp',
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar, pipelineProbeJar].join(':'),
  'dev.ets.widgettest.CoreProfilePipelineProbeKt', uiCp, join(work, 'core-profile-output'),
  join(here, 'widget_logo.svg'), join(here, 'CoreProfile.kt'), join(here, 'ImageR.java')]).trim());
process.env.JAVA_TOOL_OPTIONS = savedJavaOptions;
const stateProbeJar = compile('state-pipeline-probe', [join(here, 'StatePipelineProbe.kt')],
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar].join(':'));
console.log(run('state-profile-pipeline', 'java', ['-cp',
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar, stateProbeJar].join(':'),
  'dev.ets.widgettest.StatePipelineProbeKt', uiCp, join(work, 'state-profile-output'),
  join(here, 'StateProfile.kt'), join(here, 'UnsupportedState.kt')]).trim());

const stateOracleJar = compile('state-jvm-oracle', [join(here, 'StateJvmOracle.kt')], cp);
const expectedState = run('state-jvm', 'java', ['-cp', `${cp}:${stateOracleJar}`, 'widgetsstate.StateJvmOracleKt'])
  .trim().split('\n');
const stateOutput = join(work, 'state-profile-output/StateProfile.ets');
const stateCode = readFileSync(stateOutput, 'utf8');
const fields = [...stateCode.matchAll(/@State private (\w+): (?:boolean|number|string) = ([^;]+);/g)];
assert.deepEqual(fields.map(match => match[1]), ['__etsState_enabled', '__etsState_count', '__etsState_label']);
const callback = stateCode.match(/\.onClick\(\(\): void => \{([\s\S]*?)\n\s*\}\)/)?.[1];
const rendered = stateCode.match(/Text\((this\.__etsState_enabled \? this\.__etsState_label : "disabled")\)/)?.[1];
assert.ok(callback && rendered, 'Expected executable callback and runtime conditional in generated ETS');
const runtimeSource = `class RuntimeState {
${fields.map(match => `  ${match[1]} = ${match[2]};`).join('\n')}
  click() {${callback}\n  }
  snapshot() { return [this.${fields[0][1]}, this.${fields[1][1]}, this.${fields[2][1]}, ${rendered}].join('|'); }
}
const state = new RuntimeState();
result.push(state.snapshot());
for (let index = 0; index < 3; index++) { state.click(); result.push(state.snapshot()); }`;
const context = { result: [] };
vm.runInNewContext(runtimeSource, context, { timeout: 1000 });
assert.deepEqual(context.result, expectedState);
const stateSemantics = join(work, 'state-profile-output/state-semantics.json');
writeFileSync(stateSemantics, JSON.stringify({ expected: expectedState, actual: context.result }, null, 2) + '\n');
console.log('PASS JVM/ETS Compose state transitions preserve update order and runtime branch reads');
const inputStateProbeJar = compile('input-state-pipeline-probe', [join(here, 'InputStatePipelineProbe.kt')],
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar].join(':'));
console.log(run('input-state-profile-pipeline', 'java', ['-cp',
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar, inputStateProbeJar].join(':'),
  'dev.ets.widgettest.InputStatePipelineProbeKt', uiCp, join(work, 'input-state-output'),
  join(here, 'InputStateProfile.kt'), join(here, 'InputStateUnsupported.kt')]).trim());
const inputStateOracleJar = compile('input-state-jvm-oracle', [join(here, 'InputStateJvmOracle.kt')], cp);
const expectedInputState = run('input-state-jvm', 'java',
  ['-cp', `${cp}:${inputStateOracleJar}`, 'widgetstateinput.InputStateJvmOracleKt']).trim().split('\n');
const inputStateOutput = join(work, 'input-state-output/InputStateProfile.ets');
const inputStateCode = readFileSync(inputStateOutput, 'utf8');
const conditions = inputStateCode.split('\n').map(line => line.trim()).filter(line =>
  line.startsWith('if (') || line.startsWith('else if (')).map(line =>
  line.slice(line.indexOf('(') + 1, line.lastIndexOf(')')).replaceAll('(state as UiState)', 'state'));
const actions = [...inputStateCode.matchAll(/dispatch\("([^"]+)"\);/g)].map(match => match[1]);
assert.deepEqual(conditions, ['state.loading', '! (state.error === null)']);
assert.deepEqual(actions, ['retry', 'refresh']);
const inputRuntimeSource = `function select(state) {
  const effects = [];
  let branch;
  if (${conditions[0]}) { branch = 'loading'; }
  else if (${conditions[1]}) { effects.push('${actions[0]}'); branch = 'error'; }
  else { effects.push('${actions[1]}'); branch = 'content'; }
  return branch + '|' + effects.join();
}
result.push(...states.map(select));`;
const inputContext = { result: [], states: [
  { loading: true, error: null, content: 'ignored' },
  { loading: false, error: 'failed', content: 'ignored' },
  { loading: false, error: null, content: 'ready' },
] };
vm.runInNewContext(inputRuntimeSource, inputContext, { timeout: 1000 });
assert.deepEqual(inputContext.result, expectedInputState);
const inputStateSemantics = join(work, 'input-state-output/input-state-semantics.json');
writeFileSync(inputStateSemantics,
  JSON.stringify({ expected: expectedInputState, actual: inputContext.result, conditions, actions }, null, 2) + '\n');
console.log('PASS JVM/ETS input-state branch selection and dispatch effects match');
const pipelineTrace = JSON.parse(readFileSync(join(work, 'core-profile-pipeline.json'), 'utf8')).stderr.split('\n')
  .filter(line => line.startsWith('WIDGET_SEAM ')).map(line => line.slice('WIDGET_SEAM '.length));
const traceFile = join(work, 'core-profile-pipeline-seam.json');
writeFileSync(traceFile, JSON.stringify(pipelineTrace, null, 2) + '\n');
const entered = name => pipelineTrace.indexOf(`${name}:enter`);
const exited = name => pipelineTrace.indexOf(`${name}:exit`);
assert.equal(pipelineTrace[0], 'pipeline/ComposeWidgetPipeline.compile:enter');
assert.equal(pipelineTrace.at(-1), 'pipeline/ComposeWidgetPipeline.compile:exit');
assert.ok(entered('compose/ComposeWidgetAdapter.lower') > 0);
assert.ok(exited('compose/ComposeWidgetAdapter.lower') < entered('harmony/HarmonyWidgetBackend.lower'));
assert.ok(entered('EtsProgram.<init>') > entered('harmony/HarmonyWidgetBackend.lower'));
const emitEnter = entered('ModulesKt.emitEtsProgram');
const printerEnter = entered('EtsPrinter.program');
assert.ok(entered('EtsValidator.validate') > entered('EtsProgram.<init>'));
assert.ok(exited('EtsValidator.validate') < emitEnter);
assert.ok(pipelineTrace.slice(emitEnter, printerEnter).includes('EtsValidator.validate:exit'));
assert.ok(printerEnter > emitEnter && exited('EtsPrinter.program') < exited('ModulesKt.emitEtsProgram'));
const output = join(work, 'output/WidgetPage.ets');
const coreProfileOutput = join(work, 'core-profile-output/CoreProfile.ets');
assert.ok(existsSync(output));
assert.ok(existsSync(coreProfileOutput));
assert.ok(existsSync(stateOutput));
assert.ok(existsSync(inputStateOutput));
const diagnostics = readFileSync(join(work, 'output/diagnostics.tsv'), 'utf8').split('\n');
assert.equal(diagnostics.length, 27);
assert.ok(diagnostics.every(line => line.includes('UNSUPPORTED') && line.includes('/Unsupported.kt')));
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, implementation,
  outputs: identities([output, coreProfileOutput, stateOutput, stateSemantics,
    inputStateOutput, inputStateSemantics, traceFile,
    join(work, 'output/model.txt'), join(work, 'output/diagnostics.tsv'),
    join(work, 'state-profile-output/state-diagnostics.tsv'),
    join(work, 'input-state-output/input-state-diagnostic.tsv'),
    join(work, 'output/WidgetPage.ets.resources/base/media/widget_logo.svg'),
    join(work, 'output/WidgetPage.ets.resources/base/element/string.json')]),
  independentModelCompilation: true, adapterWithoutHarmony: true, backendWithoutCompilerOrCompose: true,
  typedTargetValidation: true, coreProfileProductionPipeline: true, composeStateProductionPipeline: true,
  composeStateJvmEtsSemantics: true, inputStateProductionPipeline: true, inputStateJvmEtsSemantics: true,
  sourceLinkedRejections: diagnostics.length + 5,
  sdk: 'separate SDK command required', nativeRendering: 'not run',
}, null, 2));
console.log('PASS Widget module isolation, resolved structure, typed ETS and explicit unsupported diagnostics');
