import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-shapes-'));
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
console.log(`Evidence: ${work}`);

function run(label, entry, sources, status = 0) {
  const output = join(work, `${label}.ets`);
  const args = [join(root, 'kotlin-ets'), '--entry', entry, '--classpath-file', cpFile,
    '--out', output, ...sources.map(name => join(here, name))];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0, `${label} partial ETS`);
  return status === 0 ? readFileSync(output, 'utf8') : result.stdout + result.stderr;
}

function runLanguage(label, sources) {
  const output = join(work, `${label}.ets`);
  const args = [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
    '--out', output, ...sources.map(name => join(here, name))];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return readFileSync(output, 'utf8');
}

const project = run('project', 'shapes.ProjectPage', ['Theme.kt', 'Page.kt']);
assert.match(project, /new EtsShape\("rounded", 4(?:\.0)?, 8(?:\.0)?, 12(?:\.0)?, 16(?:\.0)?\)/);
assert.match(project, /borderRadius\(\{ topLeft: __etsMaterialContext\.shapes\.medium\.topStart, topRight: __etsMaterialContext\.shapes\.medium\.topEnd, bottomRight: __etsMaterialContext\.shapes\.medium\.bottomEnd, bottomLeft: __etsMaterialContext\.shapes\.medium\.bottomStart \}\)/);
assert.doesNotMatch(project, /ProjectTheme\(/, 'unreachable provider must remain excluded');

const defaults = run('defaults', 'shapes.DefaultPage', ['Page.kt']);
assert.match(defaults, /new EtsShape\("rounded", 28(?:\.0)?, 28(?:\.0)?, 28(?:\.0)?, 28(?:\.0)?\)/);

const cut = run('cut', 'shapes.CutPage', ['Theme.kt', 'Page.kt']);
assert.match(cut, /import \{ PathShape as __etsPathShape \} from "@kit.ArkUI"/);
assert.match(cut, /clipShape\(new __etsPathShape\(\{ commands: "M 4 0 H 32 L 40 8 V 28 L 28 40 H 16 L 0 24 V 4 Z" \}\)\)/);

const cutValues = runLanguage('cut-values', ['CutValues.kt']);
assert.match(cutValues, /new EtsShape\("cut", 5(?:\.0)?, 5(?:\.0)?, 5(?:\.0)?, 5(?:\.0)?\)/);
assert.match(cutValues, /new EtsShape\("cut", 1(?:\.0)?, 2(?:\.0)?, 3(?:\.0)?, 4(?:\.0)?\)/);

const conflicting = run('conflicting', 'shapes.conflicting.Page', ['Conflicting.kt'], 2);
assert.match(conflicting, /Multiple distinct project MaterialTheme shapes bindings/);

const runtime = run('runtime', 'shapes.unsupported.RuntimePage', ['Unsupported.kt'], 2);
assert.match(runtime, /Runtime MaterialTheme shapes selection is unsupported/);

const percentage = run('percentage', 'shapes.unsupported.PercentagePage', ['Unsupported.kt'], 2);
assert.match(percentage, /Percentage corner sizes are unsupported/);

const custom = run('custom', 'shapes.unsupported.CustomPage', ['Unsupported.kt'], 2);
assert.match(custom, /Custom or arbitrary Shape implementations are unsupported/);

console.log('PASS project/default Material shapes, per-corner radii, static-theme conflicts and explicit unsupported shape contracts');
