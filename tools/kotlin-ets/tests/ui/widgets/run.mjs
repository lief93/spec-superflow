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
const helper = join(root, 'src/ui/compose/ComposeHelperLowering.kt');
const pipeline = join(root, 'src/ui/pipeline/ComposeWidgetPipeline.kt');
const pipelineProbe = join(here, 'CoreProfilePipelineProbe.kt');
const fixtures = ['Page.kt', 'Unsupported.kt', 'ImageR.java', 'widget_logo.svg',
  'BackendTest.kt', 'WidgetProbe.kt', 'CoreProfile.kt', 'CoreProfilePipelineProbe.kt',
  'StateProfile.kt', 'UnsupportedState.kt', 'StateJvmOracle.kt', 'StatePipelineProbe.kt',
  'PagerProfile.kt', 'PagerUnsupported.kt', 'PagerJvmOracle.kt', 'PagerPipelineProbe.kt',
  'ScrollProfile.kt', 'ScrollUnsupported.kt', 'ScrollJvmOracle.kt', 'ScrollPipelineProbe.kt',
  'LazyListProfile.kt', 'LazyListUnsupported.kt', 'LazyListJvmOracle.kt', 'LazyListPipelineProbe.kt',
  'InputStateProfile.kt', 'InputStateUnsupported.kt', 'InputStateJvmOracle.kt', 'InputStatePipelineProbe.kt',
  'ReusableCard.kt', 'HelperEntry.kt', 'HelperUnsupported.kt', 'HelperJvmOracle.kt', 'HelperPipelineProbe.kt',
  'input-state-sdk.mjs', 'helper-sdk.mjs', 'PipelineSeamAgent.java'].map(name => join(here, name));
const implementation = identities([...sources(join(root, 'src')), ...fixtures, fileURLToPath(import.meta.url), uiClasspathFile]);
for (const path of modelSources) assert.doesNotMatch(readFileSync(path, 'utf8'), /import |\bEts[A-Z]|IrCall|androidx|harmony|arkui/);
for (const path of backendSources) assert.doesNotMatch(readFileSync(path, 'utf8'), /org\.jetbrains|androidx|IrCall|ComposeWidget|ArkUiCalls/);
assert.doesNotMatch(readFileSync(adapter, 'utf8'), /Harmony|ArkUi|EtsUiElement|EtsUiAttribute|arkui:|"Stack"|"alignItems"|"fontColor"|"backgroundColor"/);
assert.doesNotMatch(readFileSync(pipeline, 'utf8'), /UiTextModule|ComposeLowering|PageText|TextModule/);
assert.doesNotMatch(readFileSync(pipelineProbe, 'utf8'), /\bEtsProgram\s*\(|\bWidget\s*[.(]|\bChildren\s*\(/);
function compile(name, inputs, classpath, options = []) {
  const jar = join(work, `${name}.jar`);
  run(`compile-${name}`, 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
    '-no-stdlib', '-no-reflect', '-classpath', classpath, ...options, ...inputs, '-d', jar]);
  return jar;
}
const modelJar = compile('model', modelSources, stdlib);
const targetJar = compile('target', sources(join(root, 'src/target')), `${stdlib}:${annotations}`);
const backendJar = compile('harmony', [...backendSources, join(here, 'BackendTest.kt')], `${stdlib}:${modelJar}:${targetJar}`);
console.log(run('backend-isolation', 'java', ['-cp', [stdlib, modelJar, targetJar, backendJar].join(':'), 'dev.ets.widgettest.BackendTestKt']).trim());
// Adapter and compiler build without any Harmony implementation on their classpath.
const compilerSources = sources(join(root, 'src')).filter(path =>
  !modelSources.includes(path) && !backendSources.includes(path) && path !== adapter && path !== helper && path !== pipeline);
const compilerJar = compile('compiler', compilerSources, `${cp}:${modelJar}`);
const adapterJar = compile('adapter', [adapter, helper], `${cp}:${modelJar}:${compilerJar}`,
  [`-Xfriend-paths=${compilerJar}`]);
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
const pagerProbeJar = compile('pager-pipeline-probe', [join(here, 'PagerPipelineProbe.kt')],
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar].join(':'));
console.log(run('pager-profile-pipeline', 'java', ['-cp',
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar, pagerProbeJar].join(':'),
  'dev.ets.widgettest.PagerPipelineProbeKt', uiCp, join(work, 'pager-profile-output'),
  join(here, 'PagerProfile.kt'), join(here, 'PagerUnsupported.kt')]).trim());
const pagerOracleJar = compile('pager-jvm-oracle', [join(here, 'PagerJvmOracle.kt')], cp);
const expectedPager = run('pager-jvm', 'java', ['-cp', `${cp}:${pagerOracleJar}`, 'widgetpager.PagerJvmOracleKt'])
  .trim().split('\n');
const pagerOutput = join(work, 'pager-profile-output/PagerProfile.ets');
const pagerCode = readFileSync(pagerOutput, 'utf8');
const pagerInitial = pagerCode.match(/@State private pager_currentPage: number = (\d+);/)?.[1];
const pagerCallback = pagerCode.match(/\.onChange\(\(index: number\): void => \{([\s\S]*?)\n\s*\}\)/)?.[1];
assert.ok(pagerInitial && pagerCallback, 'Expected typed Pager state and onChange callback in generated ETS');
const pagerRuntimeSource = `class RuntimePager {
  pager_currentPage = ${pagerInitial};
  change(index) {${pagerCallback}\n  }
}
const pager = new RuntimePager();
result.push(String(pager.pager_currentPage));
for (const page of [2, 0]) { pager.change(page); result.push(String(pager.pager_currentPage)); }`;
const pagerContext = { result: [] };
vm.runInNewContext(pagerRuntimeSource, pagerContext, { timeout: 1000 });
assert.deepEqual(pagerContext.result, expectedPager);
const pagerSemantics = join(work, 'pager-profile-output/pager-semantics.json');
writeFileSync(pagerSemantics,
  JSON.stringify({ expected: expectedPager, actual: pagerContext.result }, null, 2) + '\n');
console.log('PASS JVM/ETS Pager onChange transitions preserve currentPage state');
const scrollProbeJar = compile('scroll-pipeline-probe', [join(here, 'ScrollPipelineProbe.kt')],
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar].join(':'));
console.log(run('scroll-profile-pipeline', 'java', ['-cp',
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar, scrollProbeJar].join(':'),
  'dev.ets.widgettest.ScrollPipelineProbeKt', uiCp, join(work, 'scroll-profile-output'),
  join(here, 'ScrollProfile.kt'), join(here, 'ScrollUnsupported.kt')]).trim());
const scrollOracleJar = compile('scroll-jvm-oracle', [join(here, 'ScrollJvmOracle.kt')], cp);
const expectedScroll = run('scroll-jvm', 'java', ['-cp', `${cp}:${scrollOracleJar}`, 'widgetscroll.ScrollJvmOracleKt'])
  .trim().split('\n');
const scrollOutput = join(work, 'scroll-profile-output/ScrollProfile.ets');
const scrollCode = readFileSync(scrollOutput, 'utf8');
const scrollCallbacks = [...scrollCode.matchAll(
  /\.onScroll\(\(xOffset: number, yOffset: number\): void => \{([\s\S]*?)\n\s*\}\)/g)].map(match => match[1]);
assert.equal(scrollCallbacks.length, 2, 'Expected vertical and horizontal typed onScroll callbacks');
const scrollRuntimeSource = `class RuntimeScroll {
  vertical_offset = 12;
  horizontal_offset = 7;
  vertical(xOffset, yOffset) {${scrollCallbacks[0]}\n  }
  horizontal(xOffset, yOffset) {${scrollCallbacks[1]}\n  }
  snapshot() { return this.vertical_offset + '|' + this.horizontal_offset; }
}
const scroll = new RuntimeScroll();
result.push(scroll.snapshot());
scroll.vertical(0, 20); result.push(scroll.snapshot());
scroll.horizontal(14, 0); result.push(scroll.snapshot());
scroll.vertical(0, 4); scroll.horizontal(3, 0); result.push(scroll.snapshot());`;
const scrollContext = { result: [] };
vm.runInNewContext(scrollRuntimeSource, scrollContext, { timeout: 1000 });
assert.deepEqual(scrollContext.result, expectedScroll);
const scrollSemantics = join(work, 'scroll-profile-output/scroll-semantics.json');
writeFileSync(scrollSemantics,
  JSON.stringify({ expected: expectedScroll, actual: scrollContext.result }, null, 2) + '\n');
console.log('PASS JVM/ETS vertical and horizontal Scroll offset transitions match');
const lazyListProbeJar = compile('lazy-list-pipeline-probe', [join(here, 'LazyListPipelineProbe.kt')],
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar].join(':'));
console.log(run('lazy-list-profile-pipeline', 'java', ['-cp',
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar, lazyListProbeJar].join(':'),
  'dev.ets.widgettest.LazyListPipelineProbeKt', uiCp, join(work, 'lazy-list-profile-output'),
  join(here, 'LazyListProfile.kt'), join(here, 'LazyListUnsupported.kt')]).trim());
const lazyListOracleJar = compile('lazy-list-jvm-oracle', [join(here, 'LazyListJvmOracle.kt')], cp);
const expectedLazyList = run('lazy-list-jvm', 'java',
  ['-cp', `${cp}:${lazyListOracleJar}`, 'widgetlazy.LazyListJvmOracleKt']).trim().split('\n');
const lazyListOutput = join(work, 'lazy-list-profile-output/LazyListProfile.ets');
const lazyListCode = readFileSync(lazyListOutput, 'utf8');
const sourceMatches = [...lazyListCode.matchAll(
  /new __etsLazyArrayDataSource<([^>]+)>\((\[[^\n]*?\] as Array<[^>]+>|__etsLazyIndices\(\d+\))\)/g)];
assert.equal(sourceMatches.length, 4, 'Expected values, count, empty and row LazyForEach data sources');
const lazySources = sourceMatches.map(match => match[2].startsWith('__etsLazyIndices')
  ? Array.from({ length: Number(match[2].match(/\d+/)[0]) }, (_, index) => index)
  : JSON.parse(match[2].slice(0, match[2].indexOf(' as Array'))));
const keyExpressions = [...lazyListCode.matchAll(
  /\((\w+): (?:string|number), (\w+): number\): string => \{\n\s+return ([^;]+);/g)];
const renderedKeys = keyExpressions.map(match => match[3]);
assert.deepEqual(renderedKeys,
  ['"" + index + ":" + item', 'index.toString()', 'item', 'item']);
const keyFunctions = keyExpressions.map(match =>
  new Function(match[1], match[2], `return ${match[3]};`));
const actualLazyList = ['item|header'];
for (const [sourceIndex, values] of lazySources.entries()) {
  const category = ['values', 'count', 'empty', 'row'][sourceIndex];
  values.forEach((item, index) => {
    actualLazyList.push(`${category}|${index}|${item}|${keyFunctions[sourceIndex](item, index)}`);
  });
}
assert.deepEqual(actualLazyList, expectedLazyList);
const lazyListSemantics = join(work, 'lazy-list-profile-output/lazy-list-semantics.json');
writeFileSync(lazyListSemantics,
  JSON.stringify({ expected: expectedLazyList, actual: actualLazyList,
    sources: lazySources, keyExpressions: renderedKeys }, null, 2) + '\n');
console.log('PASS JVM/ETS lazy-list order, item/index scope and stable keys match');
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
const helperProbeJar = compile('helper-pipeline-probe', [join(here, 'HelperPipelineProbe.kt')],
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar].join(':'));
console.log(run('helper-profile-pipeline', 'java', ['-cp',
  [cp, modelJar, compilerJar, backendJar, adapterJar, pipelineJar, helperProbeJar].join(':'),
  'dev.ets.widgettest.HelperPipelineProbeKt', uiCp, join(work, 'helper-output'),
  join(here, 'ReusableCard.kt'), join(here, 'HelperEntry.kt'), join(here, 'HelperUnsupported.kt')]).trim());
const helperOracleJar = compile('helper-jvm-oracle', [join(here, 'HelperJvmOracle.kt')], cp);
const expectedHelper = run('helper-jvm', 'java',
  ['-cp', `${cp}:${helperOracleJar}`, 'widgethelpers.HelperJvmOracleKt']).trim();
const helperOutput = join(work, 'helper-output/HelperEntry.ets');
const helperCode = readFileSync(helperOutput, 'utf8');
const helperDefault = helperCode.match(/enabled: boolean = (true|false)/)?.[1] === 'true';
const callbackForwarded = /\.onClick\(onAction\)/.test(helperCode);
const scalarForwarded = /ActionCard\(title, undefined, onAction,/.test(helperCode);
const slotForwarded = /HelperEntry_content\(label\);/.test(helperCode);
assert.ok(helperDefault && callbackForwarded && scalarForwarded && slotForwarded);
const helperEffects = ['title:title'];
if (helperDefault && callbackForwarded) helperEffects.push('action');
if (slotForwarded) helperEffects.push('content:slot');
const actualHelper = helperEffects.join('|');
assert.equal(actualHelper, expectedHelper);
const helperSemantics = join(work, 'helper-output/helper-semantics.json');
writeFileSync(helperSemantics, JSON.stringify({ expected: expectedHelper, actual: actualHelper,
  helperDefault, callbackForwarded, scalarForwarded, slotForwarded }, null, 2) + '\n');
console.log('PASS JVM/ETS helper parameter, callback and content-slot effects match');
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
assert.ok(existsSync(pagerOutput));
assert.ok(existsSync(scrollOutput));
assert.ok(existsSync(lazyListOutput));
assert.ok(existsSync(inputStateOutput));
assert.ok(existsSync(helperOutput));
const diagnostics = readFileSync(join(work, 'output/diagnostics.tsv'), 'utf8').split('\n');
assert.equal(diagnostics.length, 31);
assert.ok(diagnostics.every(line => line.includes('UNSUPPORTED') && line.includes('/Unsupported.kt')));
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, implementation,
  outputs: identities([output, coreProfileOutput, stateOutput, stateSemantics,
    pagerOutput, pagerSemantics, join(work, 'pager-profile-output/pager-diagnostics.tsv'),
    scrollOutput, scrollSemantics, join(work, 'scroll-profile-output/scroll-diagnostics.tsv'),
    lazyListOutput, lazyListSemantics, join(work, 'lazy-list-profile-output/lazy-list-diagnostics.tsv'),
    inputStateOutput, inputStateSemantics, traceFile,
    helperOutput, helperSemantics,
    join(work, 'output/model.txt'), join(work, 'output/diagnostics.tsv'),
    join(work, 'state-profile-output/state-diagnostics.tsv'),
    join(work, 'input-state-output/input-state-diagnostic.tsv'),
    join(work, 'helper-output/helper-diagnostics.tsv'),
    join(work, 'output/WidgetPage.ets.resources/base/media/widget_logo.svg'),
    join(work, 'output/WidgetPage.ets.resources/base/element/string.json')]),
  independentModelCompilation: true, adapterWithoutHarmony: true, backendWithoutCompilerOrCompose: true,
  typedTargetValidation: true, coreProfileProductionPipeline: true, composeStateProductionPipeline: true,
  composeStateJvmEtsSemantics: true, pagerProductionPipeline: true, pagerJvmEtsSemantics: true,
  scrollProductionPipeline: true, scrollJvmEtsSemantics: true,
  lazyListProductionPipeline: true, lazyListJvmEtsSemantics: true,
  inputStateProductionPipeline: true, inputStateJvmEtsSemantics: true,
  composeHelperProductionPipeline: true, composeHelperJvmEtsSemantics: true,
  sourceLinkedRejections: diagnostics.length + 31,
  sdk: 'separate SDK command required', nativeRendering: 'not run',
}, null, 2));
console.log('PASS Widget module isolation, resolved structure, typed ETS and explicit unsupported diagnostics');
