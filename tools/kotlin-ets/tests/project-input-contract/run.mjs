import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { compiler, harness, identities, root, sources, hash } from '../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, 'fixtures');
const example = join(root, 'examples/adapters/project-inputs');
const exampleManifest = join(example, 'project-adapter-manifest.json');
const testModule = join(here, 'module');
const schemaPath = join(root, 'docs/project-adapter-manifest.schema.json');
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const composeCp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join(':');
const { work, run } = harness(join(here, '.work'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const api = join(work, 'dependency.jar');
run('dependency', 'bash', [compiler, '-classpath', `${cp}:${composeCp}`, join(fixtures, 'Dependency.kt'), '-d', api]);
const tool = join(work, 'tool.jar');
run('tool', 'bash', [compiler, ...sources(join(root, 'src')), ...sources(join(example, 'src')),
  ...sources(join(testModule, 'src')),
  join(here, 'ManifestMain.kt'), '-d', tool]);
const spi = join(work, 'spi/META-INF/services');
mkdirSync(spi, { recursive: true });
cpSync(join(testModule, 'META-INF/services/dev.ets.AdapterModule'), join(spi, 'dev.ets.AdapterModule'));
run('spi', 'jar', ['uf', tool, '-C', join(work, 'spi'), 'META-INF/services/dev.ets.AdapterModule']);

const manifestText = run('manifest', 'java', ['-cp', `${cp}:${tool}`, 'dev.ets.projectinputcontract.ManifestMainKt']);
const manifestPath = join(work, 'project-adapter-manifest.json');
writeFileSync(manifestPath, manifestText);
const manifest = JSON.parse(manifestText);
assert.equal(manifestText, readFileSync(exampleManifest, 'utf8'), 'checked-in portable manifest is stale');
const schema = JSON.parse(readFileSync(schemaPath, 'utf8'));
assert.equal(schema.properties.schemaVersion.const, 1);
assert.equal(manifest.schemaVersion, 1);
assert.equal(manifest.modules.length, 1);
const module = manifest.modules[0];
assert.equal(module.id, 'example.project-inputs');
assert.deepEqual(new Set(module.inputs.map(input => input.kind)), new Set([
  'token', 'color', 'font', 'dimension', 'string_resource', 'image_resource',
  'business_component', 'target_dependency',
]));
const providerInputs = module.inputs.filter(input => input.source.symbol === 'demo.projectinputs.projectInput');
assert.equal(providerInputs.length, 6);
assert.equal(new Set(providerInputs.map(input => JSON.stringify(input.source))).size, 1);
for (const input of providerInputs) {
  assert.deepEqual(input.targetParameters, [{ sourceName: 'key', targetType: 'string', optional: false }]);
  assert.ok(input.targetId && module.targetCalls.some(call => call.id === input.targetId &&
    call.parameters[0] === 'string' && call.returnType === input.targetReturnType));
}
const component = module.inputs.find(input => input.kind === 'business_component');
assert.equal(component.consumption, 'ui');
assert.deepEqual(component.contentSlot, { sourceName: 'content', required: true });
assert.equal(component.targetReturnType, 'void');

const classpath = `${cp}:${composeCp}:${api}`;
const output = join(work, 'positive');
const preflight = join(work, 'values.preflight.json');
run('values', 'java', ['-cp', `${cp}:${tool}`, 'dev.ets.MainKt', '--mode', 'language',
  '--classpath', classpath, '--out-dir', output, '--preflight-out', preflight, join(fixtures, 'Values.kt')]);
const page = join(output, 'Page.ets');
const pagePreflight = join(work, 'page.preflight.json');
run('page', 'java', ['-cp', `${cp}:${tool}`, 'dev.ets.MainKt', '--mode', 'page', '--classpath', classpath,
  '--entry', 'demo.projectinputconsumer.ProjectInputPage', '--out', page, '--preflight-out', pagePreflight,
  join(fixtures, 'Page.kt')]);
cpSync(join(here, 'ProjectInputsHost.ets'), join(output, 'ProjectInputsHost.ets'));

const values = readFileSync(join(output, 'Values.ets'), 'utf8');
for (const call of ['projectToken("enabled")', 'projectColor("brand")', 'projectFont("headline")',
  'projectDimension("spacing")', 'projectString("welcome")', 'projectImage("logo")',
  'projectDependency("clock")']) assert.ok(values.includes(call), `missing ${call}`);
const pageText = readFileSync(page, 'utf8');
assert.ok(pageText.includes('Text("Project inputs")'));
assert.ok(pageText.includes('if ('));
assert.ok(pageText.includes('ForEach(') || pageText.includes('for ('));
assert.ok(!pageText.includes('ProjectCard('));
for (const path of [join(output, 'Values.ets'), join(output, 'ProjectInputsHost.ets')]) {
  const code = readFileSync(path, 'utf8');
  assert.deepEqual(ts.createSourceFile(path, code, ts.ScriptTarget.Latest, true).parseDiagnostics, []);
}
assert.equal(JSON.parse(readFileSync(preflight)).firstUnsupportedNode, null);
assert.equal(JSON.parse(readFileSync(pagePreflight)).firstUnsupportedNode, null);

const failures = [];
for (const [label, fixture, code, kind, line, column] of [
  ['missing', 'Missing', 'PROJECT_ADAPTER_MISSING', 'project_adapter_missing', 6, 36],
  ['wrong-parameter', 'WrongParameter', 'PROJECT_ADAPTER_ARGUMENTS', 'project_adapter_arguments', 5, 37],
  ['wrong-return', 'WrongReturn', 'PROJECT_ADAPTER_RETURN_TYPE', 'project_adapter_return_type', 6, 40],
  ['void-value', 'VoidValue', 'PROJECT_ADAPTER_VOID_RESULT', 'project_adapter_void_result', 6, 39],
]) {
  const failureOut = join(work, `${label}.ets`);
  const failurePreflight = join(work, `${label}.preflight.json`);
  const failureText = run(label, 'java', ['-cp', `${cp}:${tool}`, 'dev.ets.MainKt', '--mode', 'language',
    '--classpath', classpath, '--out', failureOut, '--preflight-out', failurePreflight,
    join(fixtures, `${fixture}.kt`)], 2);
  assert.equal(existsSync(failureOut), false);
  const failure = JSON.parse(failureText.trim().split('\n').at(-1));
  assert.equal(failure.code, code);
  assert.ok(failure.source.file.endsWith(`${fixture}.kt`));
  assert.equal(failure.source.line, line);
  assert.equal(failure.source.column, column);
  const call = JSON.parse(readFileSync(failurePreflight)).calls.find(call => call.source.file.endsWith(`${fixture}.kt`));
  assert.equal(call.firstUnsupportedNode.kind, kind);
  assert.equal(call.firstUnsupportedNode.source.line, line);
  assert.equal(call.firstUnsupportedNode.source.column, column);
  failures.push({ label, code, kind, source: failure.source });
}

const implementation = identities([...sources(join(root, 'src')), ...sources(join(example, 'src')),
  ...sources(join(testModule, 'src')),
  ...sources(here), fileURLToPath(import.meta.url), schemaPath, exampleManifest]);
for (const item of implementation) assert.equal(hash(item.path), item.sha256);
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, implementation,
  manifest: { path: manifestPath, schema: schemaPath, categories: module.inputs.map(input => input.kind) },
  outputs: identities(['Values.ets', 'Page.ets', 'ProjectInputsHost.ets'].map(name => join(output, name))),
  failures,
  boundary: 'Synthetic project inputs only; no company names or API spellings.' }, null, 2));
console.log('PASS unified project inputs, manifest, target signatures, structured slot and source-linked missing input');
console.log(`Evidence: ${work}`);
