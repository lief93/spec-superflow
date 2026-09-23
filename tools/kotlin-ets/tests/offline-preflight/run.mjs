import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  buildOfflineSummary, createRedactor, parseOfflineOptions, renderOfflineDiagnosis,
} from '../../offline-preflight.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-offline-preflight-'));
console.log(`Evidence: ${work}`);

const base = ['--project', '/tmp/project', '--module', ':app', '--variant', 'debug',
  '--mode', 'page', '--entry', 'sample.Page', '--evidence', '/tmp/evidence'];
assert.equal(parseOfflineOptions(base).variant, 'debug');
for (const remove of ['--project', '--module', '--variant', '--mode', '--entry', '--evidence']) {
  const index = base.indexOf(remove);
  const args = base.filter((_, item) => item !== index && item !== index + 1);
  assert.throws(() => parseOfflineOptions(args));
}
assert.throws(() => parseOfflineOptions([...base, '--compile-task', 'compileKotlin']));
assert.throws(() => parseOfflineOptions([...base, '--unknown', 'value']));

const syntheticSource = '/tmp/project/src/main/kotlin/Page.kt';
const profile = {
  coverage: Object.fromEntries(['language_semantics', 'standard_library', 'neutral_compose_widget',
    'modifier', 'resources', 'project_dependencies'].map(name => [name,
    { total: name === 'project_dependencies' ? 1 : 0, recognized: 0,
      unsupported: name === 'project_dependencies' ? 1 : 0, percentage: name === 'project_dependencies' ? 0 : null }])),
  calls: [{ category: 'project_dependencies', resolvedSymbol: 'internal.state.provide():internal.State',
    responsibleModule: 'tools/kotlin-ets/src/adapters/AdapterModules.kt',
    source: { file: syntheticSource, line: 9, column: 7, endLine: 9, endColumn: 22 },
    argumentResolutions: [{ parameter: 'scope', resolution: 'source_default' }],
    firstUnsupportedNode: { kind: 'project_adapter_missing', message: 'Missing exact adapter binding',
      source: { file: syntheticSource, line: 9, column: 7, endLine: 9, endColumn: 22 } } }],
};
const synthetic = buildOfflineSummary({
  options: { project: '/tmp/project', module: ':app', variant: 'debug', mode: 'page', entry: 'sample.Page' },
  inputs: { task: ':app:compileDebugKotlin', sources: [syntheticSource], classpath: ['/tmp/project/build/classes'] },
  environment: { projectCompilerVersion: '2.1.10', frontendCompilerVersion: '2.1.20',
    compatibilityDecision: 'same_language_line_older_patch', arguments: [], excluded: [] },
  report: profile, diagnosis: { degradationCount: 0, degradations: [], blockingFailure: {
    code: 'PROJECT_ADAPTER_MISSING', message: 'Missing exact adapter binding' } },
  adapters: { providers: [], modules: [] }, projectResult: { ok: false }, backendExit: 2,
});
assert.equal(synthetic.status, 'blocked');
assert.equal(synthetic.targetGenerated, false);
assert.equal(synthetic.projectAdapterGaps[0].source.line, 9);
assert.equal(synthetic.explicitSourceDefaults[0].parameter, 'scope');
assert.match(renderOfflineDiagnosis(createRedactor({ project: '/tmp/project', evidence: '/tmp/evidence' })
  .value(synthetic)), /\$PROJECT\/src\/main\/kotlin\/Page\.kt:9:7/);

const project = join(work, 'project');
mkdirSync(join(project, 'src/main/kotlin'), { recursive: true });
const supported = readFileSync(join(root, 'tests/project-inputs/SupportedApp.kt'), 'utf8') +
  '\nfun defaultSpacing(base: Int, extra: Int = 8): Int = base + extra\n' +
  'fun useDefaultSpacing(): Int = defaultSpacing(16)\n';
const source = join(project, 'src/main/kotlin/App.kt');
writeFileSync(source, supported);
const compiler = spawnSync('bash', [join(root, 'tests/stdlib/compiler.sh'), '--classpath'], { encoding: 'utf8' });
assert.equal(compiler.status, 0, compiler.stdout + compiler.stderr);
const classpath = compiler.stdout.trim().split(delimiter);
const inputs = { schemaVersion: 1, project, module: ':', task: ':compileKotlin', sources: [source],
  classpath, omittedClasspath: [], compilerVersion: '2.1.20', compilerArguments: [] };
writeFileSync(join(project, 'gradlew'), `#!/usr/bin/env bash\nset -euo pipefail\nfor arg in "$@"; do\n` +
  `  case "$arg" in -PkotlinEtsInputsOutput=*) printf '%s' '${JSON.stringify(inputs)}' > "\${arg#*=}" ;; esac\n` +
  'done\n');
function runOffline(label) {
  const evidence = join(work, label);
  const args = [join(root, 'offline-preflight.mjs'), '--project', project, '--module', ':',
    '--compile-task', 'compileKotlin', '--mode', 'language', '--evidence', evidence];
  const result = spawnSync(process.execPath, args, { encoding: 'utf8', timeout: 600000,
    maxBuffer: 32 * 1024 * 1024, env: { ...process.env,
      JAVA_HOME: process.env.JAVA_HOME || '/Applications/Android Studio.app/Contents/jbr/Contents/Home',
      JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
      KOTLIN_ETS_ADAPTER_DIRS: '/must/not/be/loaded/without-an-explicit-adapter-dir' } });
  writeFileSync(join(work, `${label}.command.json`), JSON.stringify({ command: process.execPath, args,
    status: result.status, error: result.error?.message }, null, 2));
  writeFileSync(join(work, `${label}.stdout.log`), result.stdout ?? '');
  writeFileSync(join(work, `${label}.stderr.log`), result.stderr ?? '');
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return { evidence, output: JSON.parse(result.stdout) };
}
const { evidence, output } = runOffline('generated');
assert.equal(output.ok, true);
const share = join(evidence, 'share');
for (const name of ['summary.json', 'core-profile.json', 'compiler-environment.json',
  'adapter-modules.json', 'diagnosis.md', 'evidence-manifest.json']) assert.ok(existsSync(join(share, name)), name);
const summary = JSON.parse(readFileSync(join(share, 'summary.json')));
assert.equal(summary.status, 'generated');
assert.equal(summary.preflightComplete, true);
assert.equal(summary.targetGenerated, true);
assert.ok(summary.explicitSourceDefaults.some(value => value.symbol.startsWith('collector.defaultSpacing(')));
assert.equal(summary.project.root, '$PROJECT');
const manifest = JSON.parse(readFileSync(join(share, 'evidence-manifest.json')));
assert.equal(manifest.readyToPackage, true);
assert.ok(manifest.localOnly.some(value => value.path === 'raw/project-run/sources.txt'));
for (const name of ['summary.json', 'core-profile.json', 'compiler-environment.json',
  'adapter-modules.json', 'diagnosis.md', 'evidence-manifest.json']) {
  const text = readFileSync(join(share, name), 'utf8');
  assert.doesNotMatch(text, new RegExp(project.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.doesNotMatch(text, new RegExp(evidence.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
}
assert.match(readFileSync(join(share, 'diagnosis.md'), 'utf8'), /No unknown call or default value is silently accepted/);

writeFileSync(source, 'package collector\n\nimport java.util.Date\n\nfun unsupported(): Date = Date()\n');
const blocked = runOffline('blocked');
assert.equal(blocked.output.ok, true);
assert.equal(blocked.output.status, 'blocked');
const blockedSummary = JSON.parse(readFileSync(join(blocked.evidence, 'share/summary.json')));
assert.equal(blockedSummary.preflightComplete, true);
assert.equal(blockedSummary.targetGenerated, false);
assert.equal(blockedSummary.diagnosis.blockingFailure.code, 'UNSUPPORTED');
assert.ok(blockedSummary.unsupportedCalls.length > 0);
assert.equal(existsSync(join(blocked.evidence, 'raw/target.ets')), false);
assert.match(readFileSync(join(blocked.evidence, 'share/diagnosis.md'), 'utf8'), /Unsupported external constructor/);
console.log('PASS offline project preflight: explicit inputs, blocked summary, source defaults, redacted share boundary');
