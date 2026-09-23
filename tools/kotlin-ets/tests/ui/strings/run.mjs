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
const materialize = spawnSync('node', [join(root, 'string-resources.mjs'), '--res-dir', join(here, 'res'),
  '--namespace', 'strings', '--out', pack, '--symbols', join(here, 'R.txt')], { encoding: 'utf8' });
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
assert.deepEqual(base.map(x => x.value).sort(), ['Resource subtitle', 'Resource title', 'Transactions']);
assert.deepEqual(french.map(x => x.value).sort(), ['Sous-titre', 'Titre']);
assert.deepEqual(base.filter(x => x.value !== 'Transactions').map(x => x.name).sort(), french.map(x => x.name).sort());
assert.match(compile('Missing', 2), /Unsupported Android values resource.*string\.missing/);
assert.match(compile('Styled', 2), /Unsupported Android values resource.*styled/);
assert.match(compile('MissingPlural', 2), /Unsupported Android values resource.*plurals\.missing/);
assert.match(compile('Unknown', 2), /Unknown selected-build Android string resource ID: 999/);
const formatted = compile('Formatted', 0);
assert.match(formatted, /__etsFormatString/);
assert.match(formatted, /__etsFormatPlural/);
assert.match(formatted, /function __etsStringResourceId/);
assert.match(formatted, /function __etsPluralResourceId/);
assert.match(formatted, /\["Ada", 3\]/);
const plural = compile('Plural', 0);
assert.match(plural, /__etsFormatPlural/);
assert.match(plural, /getPluralStringValueSync/);
assert.match(plural, /\$r\("app\.plural\.plu_[0-9a-f]{64}"\)\.id, 2, \[2\]/);
const pluralValues = JSON.parse(readFileSync(join(work, 'Plural.ets.resources/base/element/plural.json'))).plural;
assert.deepEqual(pluralValues[0].value.map(item => item.quantity).sort(), ['one', 'other']);
assert.ok(existsSync(join(work, 'Plural.ets.resources/string-resource-origins.json')));
compile('ArrayValue', 0);
const arrayValues = JSON.parse(readFileSync(join(work, 'ArrayValue.ets.resources/base/element/strarray.json'))).strarray;
assert.deepEqual(arrayValues[0].value.map(item => item.value), ['First', 'Second']);
assert.match(compile('MissingArray', 2), /Unsupported Android values resource.*array\.missing/);
console.log('PASS string/plural typed resources, format argument order, referenced-only artifacts and explicit no-output diagnostics');
