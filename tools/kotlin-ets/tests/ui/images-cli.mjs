import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
assert.ok(process.argv[2], 'Pass the res fixture directory produced by tests/resources/run.mjs');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-images-cli-'));
console.log('Evidence: ' + work);
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 300000 });
  writeFileSync(join(work, label + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), result.stderr ?? '');
  writeFileSync(join(work, label + '.command.json'), JSON.stringify({ command, args, status: result.status }, null, 2));
  assert.equal(result.status, 0, `${label}: ${result.stderr}\n${result.stdout}`);
  return result;
}
const assets = join(work, 'assets');
run('resources', process.execPath, [join(root, 'image-resources.mjs'), '--res-dir', resolve(process.argv[2]),
  '--namespace', 'imagecontrols', '--out', assets]);
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const classpath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8'));
writeFileSync(join(work, 'classpath.txt'), classpath.join('\n'));
const ets = join(work, 'ImageControls.ets');
run('compiler', 'bash', [join(root, 'kotlin-ets'), '--entry', 'imagecontrols.ImageControls', '--out', ets,
  '--classpath-file', join(work, 'classpath.txt'), '--image-resources', join(assets, 'image-resources.properties'),
  join(here, 'ImageControls.kt'), join(here, 'ImageR.java')]);
const code = readFileSync(ets, 'utf8');
assert.match(code, /Image\(painter\)/);
assert.match(code, /Picture\(painter: Resource, description: string\)/);
assert.match(code, /alternate \?/);
assert.equal((code.match(/\$r\(["']app\.media\./g) ?? []).length, 3);
assert.doesNotMatch(code, /painterResource|R\.drawable|renderPicture/);
console.log('PASS public asset materialization -> public Kotlin/ETS CLI, preserving resource bindings and method parameters');
console.log(JSON.stringify({ ets, media: join(assets, 'media') }));
if (process.argv.includes('--sdk')) {
  const sdk = run('sdk', process.execPath, [join(here, 'basic-controls-sdk.mjs'), ets, join(assets, 'media')]);
  console.log(sdk.stdout);
}
