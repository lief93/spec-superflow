import assert from 'node:assert/strict';
import {cpSync, mkdtempSync, readFileSync, writeFileSync, existsSync, mkdirSync} from 'node:fs';
import {basename, dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
assert.ok(process.argv[2], 'Pass generated project-theme ETS');
const seed = mkdtempSync('/private/tmp/kotlin-ets-project-theme-seed-');
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260914-06/harmony', seed,
  {recursive: true, filter: path => !excluded.has(basename(path))});
for (const mode of ['base', 'dark']) {
  const file = join(seed, 'entry/src/main/resources', mode, 'element/color.json');
  const previous = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : {color: []};
  const fixture = JSON.parse(readFileSync(join(here, 'resources', mode, 'element/color.json'), 'utf8'));
  const names = new Set(fixture.color.map(c => c.name));
  previous.color = [...previous.color.filter(c => !names.has(c.name)), ...fixture.color];
  mkdirSync(dirname(file), {recursive: true});
  writeFileSync(file, JSON.stringify(previous, null, 2));
}
const result = spawnSync(process.execPath, [join(here, '../basic-controls-sdk.mjs'), resolve(process.argv[2])],
  {env: {...process.env, KOTLIN_ETS_SDK_SEED: seed}, stdio: 'inherit'});
assert.equal(result.status, 0);
