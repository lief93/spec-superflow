import assert from 'node:assert/strict';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
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
const fixtures = ['Page.kt', 'Unsupported.kt', 'ImageR.java', 'widget_logo.svg',
  'BackendTest.kt', 'WidgetProbe.kt'].map(name => join(here, name));
const implementation = identities([...sources(join(root, 'src')), ...fixtures, fileURLToPath(import.meta.url), uiClasspathFile]);
for (const path of modelSources) assert.doesNotMatch(readFileSync(path, 'utf8'), /import |\bEts[A-Z]|IrCall|androidx|harmony|arkui/);
for (const path of backendSources) assert.doesNotMatch(readFileSync(path, 'utf8'), /org\.jetbrains|androidx|IrCall|ComposeWidget|ArkUiCalls/);
assert.doesNotMatch(readFileSync(adapter, 'utf8'), /Harmony|ArkUi|EtsUiElement|EtsUiAttribute|arkui:|"Stack"|"alignItems"|"fontColor"/);
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
const compilerSources = sources(join(root, 'src')).filter(path => !modelSources.includes(path) && !backendSources.includes(path) && path !== adapter);
const compilerJar = compile('compiler', compilerSources, cp);
const adapterJar = compile('adapter', [adapter], `${cp}:${modelJar}:${compilerJar}`);
const probeJar = join(work, 'probe.jar');
run('compile-probe', 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-no-stdlib', '-no-reflect',
  '-classpath', [cp, modelJar, compilerJar, backendJar, adapterJar].join(':'), `-Xfriend-paths=${compilerJar}`,
  join(here, 'WidgetProbe.kt'), '-d', probeJar]);
console.log(run('resolved-structure', 'java', ['-cp', [cp, modelJar, compilerJar, backendJar, adapterJar, probeJar].join(':'),
  'dev.ets.widgettest.WidgetProbeKt', uiCp, join(work, 'output'), join(here, 'widget_logo.svg'),
  join(here, 'Page.kt'), join(here, 'Unsupported.kt'), join(here, 'ImageR.java')]).trim());
const output = join(work, 'output/WidgetPage.ets');
assert.ok(existsSync(output));
const diagnostics = readFileSync(join(work, 'output/diagnostics.tsv'), 'utf8').split('\n');
assert.equal(diagnostics.length, 18);
assert.ok(diagnostics.every(line => line.includes('UNSUPPORTED') && line.includes('/Unsupported.kt')));
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, implementation,
  outputs: identities([output, join(work, 'output/model.txt'), join(work, 'output/diagnostics.tsv'),
    join(work, 'output/WidgetPage.ets.resources/base/media/widget_logo.svg')]),
  independentModelCompilation: true, adapterWithoutHarmony: true, backendWithoutCompilerOrCompose: true,
  typedTargetValidation: true, sourceLinkedRejections: diagnostics.length,
  sdk: 'separate SDK command required', nativeRendering: 'not run',
}, null, 2));
console.log('PASS Widget module isolation, resolved structure, typed ETS and explicit unsupported diagnostics');
