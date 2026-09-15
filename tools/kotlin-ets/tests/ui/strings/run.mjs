import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-strings-'));
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync);
writeFileSync(join(work, 'classpath.txt'), cp.join('\n'));
console.log(`Evidence: ${work}`);
const pack = join(work, 'inputs');
const materialize = spawnSync('python3', [join(root, 'string-resources.py'), '--res-dir', join(here, 'res'),
  '--namespace', 'strings', '--out', pack], { encoding: 'utf8' });
assert.equal(materialize.status, 0, materialize.stderr);
function compile(entry, expected) {
  const output = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--entry', `strings.${entry}`, '--classpath-file', join(work, 'classpath.txt'),
    '--string-resources', pack, '--out', output, join(here, 'Page.kt'), join(here, 'R.java')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, entry + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  assert.equal(existsSync(output), expected === 0);
  assert.equal(existsSync(output + '.resources'), expected === 0);
  return expected === 0 ? readFileSync(output, 'utf8') : result.stdout;
}
const code = compile('Page', 0);
assert.match(code, /decorate\(label: string\): string/);
assert.match(code, /getContext\(\)\.resourceManager\.getStringSync\(\$r\("app\.string\.str_/);
assert.doesNotMatch(code, /Resource title|Must not be emitted/);
const base = JSON.parse(readFileSync(join(work, 'Page.ets.resources/base/element/string.json'))).string;
const french = JSON.parse(readFileSync(join(work, 'Page.ets.resources/fr/element/string.json'))).string;
assert.deepEqual(base.map(x => x.value).sort(), ['Resource subtitle', 'Resource title']);
assert.deepEqual(french.map(x => x.value).sort(), ['Sous-titre', 'Titre']);
assert.deepEqual(base.map(x => x.name).sort(), french.map(x => x.name).sort());
assert.match(compile('Missing', 2), /Unmapped string resource: strings.R.string.missing/);
assert.match(compile('Styled', 2), /Unsupported string resource.*styled/);
assert.match(compile('Formatted', 2), /Formatted stringResource/);
console.log('PASS string-valued resource calls, referenced-only resource artifacts, variants and explicit unsupported cases');
