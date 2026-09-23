import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-implicit-context-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/private/tmp/kotlin-official-frontend-probe-complete';
const dependencies = JSON.parse(readFileSync(join(probe, 'compiler-dependencies.json'), 'utf8')).map(x => x.path);
const composeClasspath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const classpathFile = join(work, 'classpath.txt');
writeFileSync(classpathFile, composeClasspath.join('\n') + '\n');
console.log(`Evidence: ${work}`);

function run(label, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result;
}

const output = join(work, 'output');
const source = [join(here, 'Helpers.kt'), join(here, 'Page.kt')];
run('page', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'implicitcontext.Page', '--classpath-file', classpathFile, '--out-dir', output, ...source]);
const page = readFileSync(join(output, 'Page.ets'), 'utf8');
const helpers = readFileSync(join(output, 'Helpers.ets'), 'utf8');
const code = helpers + '\n' + page;

for (const name of ['CrossFileFrame', 'CrossFileRelay']) assert.match(code,
  new RegExp(`${name}\\(__etsCompositionContext: EtsCompositionContext, __etsMaterialContext: EtsMaterialContext, marker: string, content: WrappedBuilder<\\[EtsCompositionContext, EtsMaterialContext\\]>`));
assert.match(code, /\.builder\(__etsCompositionContext, new EtsMaterialContext\(/,
  'Surface forwards the scoped Material context without changing the CompositionLocal context');
assert.match(page, /CrossFileRelay\(new EtsCompositionContext\([\s\S]*?\), __etsMaterialContext, "outer",/);
assert.match(page, /CrossFileRelay\(__etsCompositionContext, __etsMaterialContext, "inner",/);
assert.match(page, /CompositionLocalContent_[0-9]+\(__etsCompositionContext, __etsMaterialContext, evaluatedName\("theme-first"\), evaluatedCount\(1\)\)/);
assert.match(page, /MaterialThemeContent_[0-9]+\(new EtsCompositionContext\([\s\S]*?new EtsMaterialContext\(/,
  'both provider introduction orders bind the declared Composition and Material identities');
assert.match(page, /new ConstraintData_[0-9]+\(new EtsCompositionContext\([\s\S]*?__etsMaterialContext\)/,
  'BoxWithConstraints captures simultaneous contexts in declared identity order');
assert.match(code, /__etsMergeTextStyle\([\s\S]*?typography\.labelSmall\), __etsMaterialContext\.value\.shapes\)/,
  'TextButton and ProvideTextStyle keep the merged style and shapes in their declared fields');
for (const value of ['evaluatedName("theme-first")', 'evaluatedCount(1)', 'evaluatedCount(2)',
  'evaluatedName("shadowed")', 'evaluatedCount(3)', 'evaluatedName("local-first")']) {
  assert.equal((code.match(new RegExp(value.replace(/[()]/g, '\\$&'), 'g')) ?? []).length, 1,
    `${value} must evaluate once`);
}
assert.ok(page.indexOf('evaluatedCount(2)') < page.indexOf('evaluatedName("shadowed")'),
  'provider source argument order is preserved independently of context order');

const implementation = readdirSync(join(root, 'src'), { recursive: true })
  .filter(path => path.endsWith('.kt') && !path.endsWith('Main.kt') && !path.endsWith('Printer.kt') &&
    !path.startsWith('output/') && !path.startsWith('ui/pipeline/'))
  .sort().map(path => join(root, 'src', path));
const contractJar = join(work, 'context-contract.jar');
run('contract-compile', 'java', ['-cp', dependencies.join(':'), 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
  '-no-stdlib', '-no-reflect', '-classpath', dependencies.join(':'), '-d', contractJar,
  ...implementation, join(here, 'ContextBindingProbe.kt')]);
const contract = run('contract', 'java', ['-cp', `${contractJar}:${dependencies.join(':')}`,
  'dev.ets.ContextBindingProbeKt']);
assert.match(contract.stdout, /PASS identity-ordered implicit contexts/);
console.log('PASS simultaneous contexts, introduction order, shadowing, constraints, cross-file helpers, slots, single evaluation, missing and wrong-type rejection');
