import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-modifier-arguments-'));
console.log('Evidence: ' + work);
const cp = join(work, 'classpath.txt');
writeFileSync(cp, JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json')).filter(existsSync).join('\n'));
for (const [entry, status, diagnostic] of [['Page', 0], ['RequiredRoot', 0], ['Dynamic', 2, /Dynamic Modifier operands/], ['Effectful', 2, /Effectful Modifier operands/], ['DefaultFailure', 2, /Unsupported TextAlign value: Left/]]) {
  const output = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--entry', 'modifierarguments.' + entry, '--classpath-file', cp,
    '--out', output, join(here, 'Page.kt'), join(here, 'BadDefault.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, entry + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0);
  if (status) assert.match(result.stdout, diagnostic);
  else if (entry === 'Page') {
    const source = readFileSync(output, 'utf8');
    assert.equal(source.match(/function Forward_Modifier1\(/g)?.length, 1);
    assert.match(source, /Forward_Modifier1\(text: string\)/);
    assert.match(source, /Card_Modifier1\(text: string\)/);
    assert.match(source, /Card_Modifier2\(text: string\)/);
    assert.match(source, /Card\(modifier: EtsEmptyModifier, text: string\)/);
    assert.match(source, /\.width\("100%"\)\.height\(24(?:\.0)?\)/);
    assert.match(source, /\.width\(80(?:\.0)?\)\.height\(24(?:\.0)?\)/);
    assert.match(source, /Forward_Modifier1\("first"\)/);
    assert.match(source, /Forward_Modifier1\("second"\)/);
    assert.match(source, /Card_Modifier3\("horizontal"\)/);
    assert.match(source, /Card_Modifier3\("horizontal-again"\)/);
    assert.match(source, /Card_Modifier4\("vertical"\)/);
    assert.match(source, /Card_Modifier5\("all"\)/);
    assert.match(source, /padding\(\{ left: 8(?:\.0)?, right: 8(?:\.0)?, top: 0, bottom: 0 \}\)/);
    assert.match(source, /padding\(\{ left: 0, right: 0, top: 8(?:\.0)?, bottom: 8(?:\.0)? \}\)/);
  } else {
    const source = readFileSync(output, 'utf8');
    assert.doesNotMatch(source, /@Entry\s+@Component\s+export struct RequiredRoot/);
    assert.match(source, /@Component\s+export struct RequiredRoot/);
    assert.match(source, /@Require @Prop modifier: EtsEmptyModifier;/);
    assert.match(source, /Card_Modifier1\("root"\)/);
    assert.match(source, /\.width\("100%"\)\.height\("100%"\)/);
  }
  if (entry === 'DefaultFailure') {
    const error = JSON.parse(result.stdout.trim().split('\n').at(-1));
    assert.equal(resolve(error.source.file), join(here, 'BadDefault.kt'));
    assert.equal(error.source.line, 7);
  }
}
console.log('PASS static Modifier forwarding, source methods, deduplication, variants and dynamic/effectful rejection');
