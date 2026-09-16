import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-ui-tests-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const dependencies = JSON.parse(readFileSync(join(probe, 'compiler-dependencies.json'), 'utf8')).map(x => x.path);
const classpath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join(':');
const classpathFile = join(work, 'classpath.txt');
writeFileSync(classpathFile, classpath.split(':').join('\n') + '\n');
const java = process.env.JAVA_HOME ? join(process.env.JAVA_HOME, 'bin/java') : '/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/java';
const fixture = join(root, 'fixtures/Page.kt');
const cli = join(root, 'kotlin-ets');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const implementation = readdirSync(join(root, 'src'), { recursive: true }).filter(path => path.endsWith('.kt')).sort()
  .map(file => { const path = join(root, 'src', file); return { path, sha256: hash(path) }; });
const sourceInputs = new Map();
console.log(`Evidence: ${work}`);

function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status, stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (result.error) throw result.error;
  return result;
}
function generate(label, source, entry, accepted = true) {
  sourceInputs.set(source, hash(source));
  const output = join(work, `${label}.ets`);
  const result = run(label, 'bash', [cli, '--mode', 'page', '--unsupported-policy', 'error', '--entry', entry, '--classpath-file', classpathFile, '--out', output, source]);
  assert.equal(result.status, accepted ? 0 : 2, `${label}: ${result.stdout}\n${result.stderr}`);
  const report = JSON.parse(result.stdout.trim().split('\n').at(-1));
  assert.equal(report.ok, accepted);
  if (accepted) return readFileSync(output, 'utf8');
  assert.equal(existsSync(output), false, 'failed translation must not leave plausible output');
  assert.equal(report.code, 'UNSUPPORTED');
  assert.equal(resolve(report.source.file), resolve(source));
  assert.ok(report.source.start >= 0 && report.source.end > report.source.start, 'source-linked offsets');
  return report;
}

function assertEntryContainer(output, entryCall) {
  const entryBuild = output.slice(output.lastIndexOf('  build() {'));
  assert.equal(entryBuild, [
    '  build() {',
    '    Stack({ alignContent: Alignment.TopStart }) {',
    `      ${entryCall}`,
    '    }.width("100%").height("100%")',
    '  }',
    '}',
    '',
  ].join('\n'), 'SDK 10905210: @Entry.build requires a native container around the source builder');
}

function helperJavascript(output) {
  const helpers = output.slice(0, output.indexOf('\n@Entry'));
  // Only ordinary declarations belong in the host oracle; the SDK consumes all builders.
  const parsed = ts.createSourceFile('helpers.ts', helpers, ts.ScriptTarget.ES2022, true);
  const declarations = parsed.statements.filter(statement => {
    if (ts.isImportDeclaration(statement)) return false;
    // The pinned SDK parser retains function decorators in illegalDecorators before ArkUI transformation.
    const decorators = statement.decorators ?? statement.illegalDecorators ?? [];
    return !decorators.some(decorator => ts.isIdentifier(decorator.expression) && decorator.expression.text === 'Builder');
  })
    .map(statement => statement.getFullText(parsed)).join('\n');
  const result = ts.transpileModule(declarations, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(result.diagnostics, []);
  return result.outputText;
}

const helperProjection = helperJavascript(`@Builder
export function NativeLabel(text: string) { Column() { Text(text).fontSize(16) }.width(20) }
export function unchanged(value: number): number { return value + 1; }
\n@Entry`);
assert.ok(!helperProjection.includes('NativeLabel'), 'host oracle excludes native builder declarations through their AST decorator');
assert.equal(vm.runInNewContext(helperProjection + '\nunchanged(5)', { exports: {} }), 6);

const composableValues = generate('composable-values', join(here, 'ComposableValues.kt'), 'composablevalues.ComposableValues');
const valueJs = helperJavascript(composableValues);
assert.equal(vm.runInNewContext(valueJs + '\ngetRawString("title") + "|" + getRawString("other")', { exports: {} }, { timeout: 1000 }),
  'Field Notes|Unknown other', 'pure @Composable value helpers must remain executable ordinary functions');
assert.ok(composableValues.includes('Text(getRawString("title"))'), 'Text consumes the shared-printer resolved value helper');
assert.ok(!composableValues.includes('this.getRawString('), 'value helper is not a UI builder');

const typedExpressions = generate('typed-expressions', join(here, 'TypedExpressions.kt'), 'typedexpressions.TypedExpressions');
assertEntryContainer(typedExpressions, 'this.TypedExpressions(0.5, true)');
assert.ok(typedExpressions.includes('.width(ratio * 100 + "%")'), 'fill uses typed arithmetic and a string literal through the shared printer');
assert.ok(typedExpressions.includes('.backgroundColor(active ? 4294901760 : 4278190080)'),
  'resolved Color mapping constructs numeric literals and a typed conditional');
assert.ok(typedExpressions.includes('.id("typed \\"value\\"")'), 'source string escaping comes from the shared printer');

const materialText = generate('material-text', join(here, 'MaterialText.kt'), 'materialtext.MaterialText');
assert.ok(materialText.includes('}.alignItems(VerticalAlign.Center).justifyContent(FlexAlign.Center)'),
  'Material Button content retains its implicit centered Row, including multi-root source slots');
for (const [label, size, lineHeight, weight, tracking] of [
  ['Body', 16, 24, 400, 0.5], ['Large body', 24, 24, 400, 0.5],
  ['Wrapped label', 14, 20, 500, 0.1], ['Explicit label', 16, 20, 500, 0.1],
  ['Body restored', 16, 24, 400, 0.5],
]) {
  const text = materialText.split('\n').find(line => line.includes(`Text("${label}")`));
  assert.ok(text?.includes(`.attributeModifier(new __etsMaterialTypography(${size}, ${lineHeight}, ${weight}, ${tracking}))`),
    `${label} must inherit the pinned Material3 typography without duplicating source expressions`);
}
assert.ok(materialText.includes('metrics.descent - metrics.ascent - fp2px(this.lineHeight)'), 'leading derives from native font metrics, not a size multiplier');
assert.ok(materialText.includes('.padding({ top: leading, bottom: leading })'), 'first/last-line leading is outer padding, not a per-line height increase');
assert.match(generate('unsupported-text-provider', join(here, 'UnsupportedTextProvider.kt'), 'negative.UnknownPage', false).message, /ProvideTextStyle/);
assert.match(generate('unsupported-text-contexts', join(here, 'UnsupportedTextContexts.kt'), 'negative.UnknownPage', false).message, /different inherited Material text styles/);
const unsupportedValueSource = join(here, 'UnsupportedComposableValue.kt');
const unsupportedValue = generate('unsupported-composable-value', unsupportedValueSource, 'negative.UnknownPage', false);
assert.match(unsupportedValue.message, /^Unsupported string concatenation operand: androidx\.compose\.material3\.Typography$/);
assert.equal(readFileSync(unsupportedValueSource, 'utf8').slice(unsupportedValue.source.start, unsupportedValue.source.end),
  'typography', 'official concatenation normalization retains the resolved property token source');
assert.match(generate('unsupported-composable-value-ui', join(here, 'UnsupportedComposableValueUi.kt'), 'negative.UnknownPage', false).message,
  /Source UI builder cannot execute inside a value helper/, 'a value helper cannot silently call an undefined UI function');

const touchTargets = generate('touch-targets', join(here, 'TouchTargets.kt'), 'touch.TouchTargets');
assert.ok(touchTargets.includes('__etsNearestTouch(items, 3.0, 22.0, 10.0)'), 'touch bounds derive from changed source dimensions');
assert.match(generate('unsupported-touch-topology', join(here, 'UnsupportedTouchTopology.kt'), 'negative.UnknownPage', false).message,
  /Minimum touch target arbitration/, 'unbounded topology must not silently revert to nominal-only native clicks');
assert.match(generate('unsupported-disabled-touch', join(here, 'UnsupportedDisabledTouch.kt'), 'negative.UnknownPage', false).message,
  /requires enabled targets/, 'disabled candidates cannot silently participate in nearest-target arbitration');
const source = generate('fixture', fixture, 'sample.Page');
assert.ok(source.startsWith('import __etsDrawing from "@ohos.graphics.drawing";\n'), 'structured module imports precede stdlib declarations');
assert.ok(source.includes('__etsNearestTouch(items, 4.0, 20.0, 8.0)'), 'overlapping expanded targets use nearest-child arbitration');
const touchRuntime = helperJavascript(source);
for (const [x, expected] of [[62, '0'], [90, '1'], [103, '1'], [104, '2'], [105, '2'], [106, '2'], [118, '2'], [146, '3']]) {
  const items = Array.from({ length: 4 }, (_, index) => ({ id: String(index), x: x - 48 - 28 * index, y: 8 })).reverse();
  assert.equal(vm.runInNewContext(touchRuntime + '\n__etsNearestTouch(items, 4, 20, 8).id',
    { exports: {}, items, TouchTestStrategy: { DEFAULT: 0, FORWARD: 2 } }, { timeout: 1000 }), expected,
    'native-probe specified overlap points select the nearest nominal pointer rectangle');
}
assertEntryContainer(source, 'this.Page(12, 4)');
assert.ok(!source.includes('uiTemporary'), 'immutable compiler temporaries must not introduce single-read builders');
assert.ok(!source.includes('ComposeContentSlot'), 'multi-root content must remain in its source parent layout');
assert.ok(source.split('Stack({ alignContent: Alignment.TopStart })').length - 1 <= 4,
  'only the entry, source Box, and ordering-required modifier boundaries need Stacks');
for (const marker of ['struct Page', 'Page(base: number', 'PageFrame(title: string', 'ContentPanel(spacing: number',
  'content: WrappedBuilder<[]>', 'content.builder()', 'Swiper(this.pagerState_controller)', 'this.pagerState_currentPage',
  'this.callbackCount', '.onChange(', '.changeIndex(', '.id("pager")', 'length: 4']) {
  assert.ok(source.includes(marker), `missing semantic/structural seam: ${marker}`);
}
assert.ok(!source.includes('layoutPx'));
assert.ok(!source.includes('() => {}'), 'no empty content substitution');
assert.ok(source.includes('base + extra'), 'source arithmetic survives');
assert.equal(source.split('pageModel(page)').length - 1, 1, 'source model initializer evaluates once per page body');
assert.ok(source.includes('model: Model'), 'source model local retains a typed binding');

const kotlinHome = dependencies.find(path => path.includes('/kotlin-compiler-embeddable/')).split('/org.jetbrains.kotlin/')[0];
const pluginRoot = join(kotlinHome, 'org.jetbrains.kotlin/kotlin-compose-compiler-plugin-embeddable/2.1.20');
const plugin = readdirSync(pluginRoot).map(hash => join(pluginRoot, hash, 'kotlin-compose-compiler-plugin-embeddable-2.1.20.jar')).find(existsSync);
assert.ok(plugin, 'actual Compose compiler plugin prerequisite');
const classes = join(work, 'jvm');
const compiled = run('fixture-jvm-compile', java, ['-cp', dependencies.join(':'), 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
  '-no-stdlib', '-no-reflect', '-classpath', classpath, `-Xplugin=${plugin}`, '-d', classes, fixture, join(here, 'FixtureOracle.kt')]);
assert.equal(compiled.status, 0, compiled.stderr);
const oracle = run('fixture-jvm-oracle', java, ['-cp', `${classes}:${classpath}`, 'ui.test.FixtureOracleKt']);
assert.equal(oracle.status, 0, oracle.stderr);
const values = vm.runInNewContext(helperJavascript(source) + `\n[0,1,2,3,2].map(page => { const model = pageModel(page); return page + ':' + model.title + ':' + model.detail + ':' + buttonLabel(page); }).join('\\n')`, { exports: {} }, { timeout: 1000 });
assert.equal(values, oracle.stdout.trim(), 'ordinary source methods execute identically on JVM and generated target');

const renamed = join(work, 'NotesPage.kt');
writeFileSync(renamed, readFileSync(fixture, 'utf8')
  .replaceAll('PageFrame', 'NotebookFrame').replaceAll('ContentPanel', 'NotebookPanel')
  .replaceAll('fun Page(', 'fun NotesPage(').replaceAll('buttonLabel', 'actionTitle')
  .replaceAll('callbackCount', 'clickTotal').replaceAll('pagerState', 'carousel')
  .replaceAll('base: Int = 12', 'base: Int = 7').replaceAll('extra: Int = 4', 'extra: Int = 5'));
const renamedOutput = generate('renamed', renamed, 'sample.NotesPage');
assertEntryContainer(renamedOutput, 'this.NotesPage(7, 5)');
for (const marker of ['struct NotesPage', 'NotebookFrame', 'NotebookPanel', 'actionTitle', 'this.clickTotal', 'this.carousel_currentPage', 'this.NotesPage(7, 5)']) {
  assert.ok(renamedOutput.includes(marker), `renamed source lost ${marker}`);
}
assert.ok(!renamedOutput.includes('this.pagerState'), 'bindings follow symbols, not fixture names');
const ordered = generate('modifier-order', join(here, 'ModifierOrder.kt'), 'order.ModifierOrder');
const lines = ordered.split('\n');
const depth = line => line.length - line.trimStart().length;
const clickLayers = lines.filter(line => line.includes('}.onClick(') || line.includes('.onClick('));
const paddingLayers = lines.filter(line => line.includes('.padding(4)'));
const widthLayers = lines.filter(line => line.includes('.width(20)'));
const heightLayers = lines.filter(line => line.includes('.height(8)'));
assert.equal(clickLayers.length, 2);
assert.equal(paddingLayers.length, 2);
assert.ok(depth(clickLayers[0]) <= depth(paddingLayers[0]), 'click-before-padding includes padding in its nominal pointer bounds');
assert.ok(depth(clickLayers[1]) > depth(paddingLayers[1]), 'click-after-padding has inner nominal pointer bounds; minimum touch expansion is separate');
for (let index = 0; index < 2; index++) {
  assert.ok(depth(widthLayers[index]) > depth(paddingLayers[index]), '20vp width is inside 4vp outer padding');
  assert.ok(depth(heightLayers[index]) > depth(paddingLayers[index]), '8vp height is inside 4vp outer padding');
  if (index === 1) assert.ok(!clickLayers[index].includes('.padding('), 'click-after-padding does not paint or lay out its outer padding');
}
assert.match(generate('unsupported-api', join(here, 'UnsupportedApi.kt'), 'negative.UnknownPage', false).message, /LazyColumn/);
assert.match(generate('unsupported-modifier', join(here, 'UnsupportedModifier.kt'), 'negative.UnknownPage', false).message, /rotate/);
assert.match(generate('unsupported-text-argument', join(here, 'UnsupportedTextArgument.kt'), 'negative.UnknownPage', false).message, /letterSpacing/);
assert.match(generate('unsupported-layout-argument', join(here, 'UnsupportedLayoutArgument.kt'), 'negative.UnknownPage', false).message, /verticalArrangement/);
assert.match(generate('unsupported-pager-count', join(here, 'UnsupportedPagerCount.kt'), 'negative.UnknownPage', false).message, /pageCount/);
assert.match(generate('unsupported-coroutine', join(here, 'UnsupportedCoroutine.kt'), 'negative.UnknownPage', false).message, /coroutine/);
assert.match(generate('unsupported-launch-value', join(here, 'UnsupportedLaunchValue.kt'), 'negative.UnknownPage', false).message,
  /Unsupported resolved platform expression: kotlinx.coroutines.launch/, 'effect-only pager adapter must never fabricate a Job value');
const sourceValues = generate('source-values', join(here, 'SourceValues.kt'), 'values.SourceValues');
assert.equal(sourceValues.split('counter.next()').length - 1, 2, 'used and unused effectful local initializers each evaluate once');
assert.ok(sourceValues.includes('label: string'), 'both Text reads share the captured source value');
assert.ok(sourceValues.includes('unused: string'), 'unused declaration still evaluates its effectful initializer');
const temporaries = generate('compiler-temporaries', join(here, 'CompilerTemporaries.kt'), 'temporaries.CompilerTemporaries');
assert.ok(temporaries.includes('Text(value.immutable)'), 'default immutable property read stays directly in Text');
assert.ok(!temporaries.includes('Text(value.mutable)'), 'mutable read must remain captured before a later argument can mutate it');
assert.equal(temporaries.split('value.effectText()').length - 1, 1, 'effectful compiler temporary evaluates once');
assert.equal(temporaries.split('value.mutate()').length - 1, 1, 'later argument effect is neither duplicated nor dropped');
const slotLayouts = generate('slot-layouts', join(here, 'SlotLayouts.kt'), 'slotlayouts.SlotLayouts');
assert.equal(slotLayouts.split('content.builder()').length - 1, 2, 'both Column and Row invoke slots directly');
assert.ok(!slotLayouts.includes('ComposeContentSlot'));
assert.ok(slotLayouts.includes('HorizontalFrame(content: WrappedBuilder<[]>)'));
assert.equal(slotLayouts.split('Stack({ alignContent: Alignment.TopStart })').length - 1, 1,
  'simple Text tags and dimensions add no layout wrappers; only native entry bridge remains');
const layers = generate('modifier-layers', join(here, 'ModifierLayers.kt'), 'layers.ModifierLayers');
assert.ok(layers.includes('.width(20).height(8).backgroundColor(4278190080).id("direct")'),
  'independent dimensions, paint, and tag belong directly on the source Box');
assert.ok(layers.includes('.width(28).height(16).padding(4)'), 'padding inside fixed size preserves the outer constraint');
assert.ok(layers.includes('.width("100%").height("100%").backgroundColor(4287137928).id("inside")'),
  'inner paint receives the remaining content size after padding');
assert.ok(layers.includes('.backgroundColor(4278190080).padding(4)'), 'outer paint includes padding');
assert.ok(layers.includes('.backgroundColor(4294901760).id("paint")'), 'inner paint remains independently ordered');
assert.ok(!layers.includes('.width(40)'), 'later preferred size cannot override an already fixed outer width');
assert.ok(layers.includes('.backgroundColor(0).id("alpha")'), 'transparent inner paint does not overwrite outer paint');
assert.equal(layers.split('Stack({ alignContent: Alignment.TopStart })').length - 1, 12,
  'six source Boxes plus five necessary ordering boundaries and the native entry bridge');

const conditionalUi = generate('conditional-ui', join(here, 'ConditionalUi.kt'), 'conditionalui.ConditionalUi');
assert.ok(conditionalUi.includes('if (active) {') && conditionalUi.includes('.id("Active")') &&
  conditionalUi.includes('.id("Inactive")'), 'UI condition keeps the parameter and both branches despite the default preview state');
assert.ok(!conditionalUi.includes('__etsMaterialTypography'), 'unused framework runtime must not be emitted');

const moduleSources = ['Models.kt', 'Screen.kt'].map(name => join(here, 'modules', name));
moduleSources.forEach(path => sourceInputs.set(path, hash(path)));
const moduleDirectory = join(work, 'modules');
const moduleArgs = [cli, '--mode', 'page', '--entry', 'multimodule.Page', '--classpath-file', classpathFile,
  '--out-dir', moduleDirectory, ...moduleSources];
const moduleRun = run('ui-modules', 'bash', moduleArgs);
assert.equal(moduleRun.status, 0, moduleRun.stdout + moduleRun.stderr);
assert.deepEqual(readdirSync(moduleDirectory).sort(), ['Models.ets', 'Screen.ets']);
const screen = readFileSync(join(moduleDirectory, 'Screen.ets'), 'utf8');
const models = readFileSync(join(moduleDirectory, 'Models.ets'), 'utf8');
assert.match(screen, /import \{ Model \} from "\.\/Models"/);
assert.match(screen, /import \{ label \} from "\.\/Models"/);
assert.ok(screen.includes('Page(seed: number = 2)') && screen.includes('Text(label(new Model(seed)))'));
assert.ok(!screen.includes('class Model') && !screen.includes('function label'));
assert.ok(models.includes('export class Model') && models.includes('export function label(model: Model)'));
assert.ok(!models.includes('@Entry'));
const moduleHashes = readdirSync(moduleDirectory).map(name => ({ path: join(moduleDirectory, name),
  sha256: hash(join(moduleDirectory, name)), entry: name === 'Screen.ets' }));
const overwrite = run('ui-modules-no-overwrite', 'bash', moduleArgs);
assert.equal(overwrite.status, 1);
for (const file of moduleHashes) assert.equal(hash(file.path), file.sha256);

const ownershipSources = ['Widgets.kt', 'Screen.kt', 'Services.kt'].map(name => join(here, 'ownership', name));
ownershipSources.forEach(path => sourceInputs.set(path, hash(path)));
const ownershipDirectory = join(work, 'ownership');
const ownershipRun = run('source-builder-modules', 'bash', [cli, '--mode', 'page', '--entry', 'ownership.OwnershipPage',
  '--classpath-file', classpathFile, '--out-dir', ownershipDirectory, ...ownershipSources]);
assert.equal(ownershipRun.status, 0, ownershipRun.stdout + ownershipRun.stderr);
assert.deepEqual(readdirSync(ownershipDirectory).sort(), ['Screen.ets', 'Services.ets', 'Widgets.ets']);
const widgets = readFileSync(join(ownershipDirectory, 'Widgets.ets'), 'utf8');
const ownershipPage = readFileSync(join(ownershipDirectory, 'Screen.ets'), 'utf8');
for (const name of ['Leaf', 'Chain', 'Action', 'Frame']) assert.ok(widgets.includes(`export function ${name}(`));
assert.ok(widgets.includes('function PrivateCaption(label: string)') && !widgets.includes('export function PrivateCaption'));
const widgetAst = ts.createSourceFile('Widgets.ets', widgets, ts.ScriptTarget.Latest, true);
const widgetFunctions = widgetAst.statements.filter(ts.isFunctionDeclaration);
assert.deepEqual(widgetFunctions.map(node => node.name.text), ['PrivateCaption', 'Leaf', 'Chain', 'Action', 'Frame']);
for (const functionNode of widgetFunctions) {
  function checkReceiver(node) {
    assert.notEqual(node.kind, ts.SyntaxKind.ThisKeyword, 'hoisted methods must not acquire a page receiver');
    ts.forEachChild(node, checkReceiver);
  }
  checkReceiver(functionNode);
}
assert.ok(ownershipPage.includes('struct OwnershipPage') && ownershipPage.includes('this.count'));
assert.match(ownershipPage, /import \{ Chain \} from "\.\/Widgets"/);
assert.match(ownershipPage, /import \{ Action \} from "\.\/Widgets"/);
for (const name of readdirSync(ownershipDirectory)) moduleHashes.push({ path: join(ownershipDirectory, name),
  sha256: hash(join(ownershipDirectory, name)), entry: name === 'Screen.ets', relativePath: 'ownership/' + name });

const productionSources = readdirSync(join(root, 'src'), { recursive: true })
  .filter(path => path.endsWith('.kt')).sort().map(path => join(root, 'src', path));
const typedJar = join(work, 'typed-boundary.jar');
const typedCompile = run('typed-boundary-compile', java, ['-cp', dependencies.join(':'),
  'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-no-stdlib', '-no-reflect',
  '-classpath', dependencies.join(':'), '-d', typedJar, ...productionSources, join(here, 'TypedBoundaryProbe.kt')]);
assert.equal(typedCompile.status, 0, typedCompile.stderr);
const typedProbe = run('typed-boundary-probe', java, ['-cp', `${typedJar}:${dependencies.join(':')}`,
  'ui.test.TypedBoundaryProbeKt', classpath, fixture, join(here, 'UnifiedApi.kt')]);
assert.equal(typedProbe.status, 0, `${typedProbe.stdout}\n${typedProbe.stderr}`);
assert.ok(typedProbe.stdout.includes('PASS typed UI bindings'));
for (const file of implementation) assert.equal(hash(file.path), file.sha256, 'Compiler changed during UI regression');
for (const [file, sha256] of sourceInputs) assert.equal(hash(file), sha256, 'Fixture changed during UI regression');
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, implementation,
  moduleOutputs: moduleHashes,
  sourceInputs: [...sourceInputs].map(([path, sha256]) => ({ path, sha256 })),
  outputs: readdirSync(work).filter(name => name.endsWith('.ets')).map(name => ({ path: join(work, name), sha256: hash(join(work, name)) })) }, null, 2));
console.log('PASS source -> official K2 -> CLI -> ETS, JVM/target helper oracle, renamed inputs, source-linked rejection');
console.log('SDK build and live pager/callback assertions remain the verification owner\'s gates.');
