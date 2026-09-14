import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync, symlinkSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const script = resolve(here, '../../image-resources.mjs');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
// Fixed local synthetic one-pixel images, not user/company or downloaded assets.
const bitmaps = JSON.parse(readFileSync(join(here, 'fixtures/bitmaps.json')));
const png = Buffer.from(bitmaps.png, 'base64');
function resource(res, path, payload) {
  const destination = join(res, path);
  mkdirSync(dirname(destination), { recursive: true });
  writeFileSync(destination, payload);
}
function call(label, res, namespace = 'example', output = join(work, label), expectedError) {
  const args = [script, '--res-dir', res, '--namespace', namespace, '--out', output];
  const result = spawnSync(process.execPath, args, { encoding: 'utf8', timeout: 30000 });
  writeFileSync(join(work, `${label}-command.json`), JSON.stringify({ args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
  if (result.error) throw result.error;
  if (expectedError) {
    assert.equal(result.status, 1, result.stdout + result.stderr);
    assert.match(result.stderr, expectedError);
    return output;
  }
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const properties = readFileSync(join(output, 'image-resources.properties'), 'utf8');
  assert.match(properties, /^[\x00-\x7f]*$/);
  const mapping = Object.fromEntries(properties.trim().split('\n').map(line => line.split(' = ')));
  assert.ok(Object.keys(mapping).every(key => key.startsWith(`${namespace}.R.drawable.`)));
  assert.ok(Object.values(mapping).every(value => /^[a-z][a-z0-9_]*$/.test(value)));
  return { output, properties, mapping };
}
const res = join(work, 'res');
resource(res, 'drawable/banner.png', png);
resource(res, 'drawable-nodpi/logo.png', png);
resource(res, 'drawable/second.xml', readFileSync(join(here, 'fixtures/static.xml')));
const first = call('positive', res);
assert.equal(Object.keys(first.mapping).length, 3);
assert.equal(new Set(Object.values(first.mapping)).size, 3);
assert.deepEqual(readFileSync(join(first.output, 'media', `${first.mapping['example.R.drawable.banner']}.png`)), png);
assert.deepEqual(readFileSync(join(first.output, 'media', `${first.mapping['example.R.drawable.logo']}.png`)), png);
const svg = readFileSync(join(first.output, 'media', `${first.mapping['example.R.drawable.second']}.svg`), 'utf8');
assert.match(svg, /width="24" height="12" viewBox="0 0 24 12"/);
assert.match(svg, /fill="#336699"/);
assert.match(svg, /d="M0,0 L24,0 L24,12 L0,12 Z"/);
const formats = join(work, 'formats-res');
resource(formats, 'drawable/photo.jpg', Buffer.from(bitmaps.jpeg, 'base64'));
resource(formats, 'drawable/photo_alias.jpeg', Buffer.from(bitmaps.jpeg, 'base64'));
resource(formats, 'drawable-nodpi/web.webp', Buffer.from(bitmaps.webp, 'base64'));
const copiedFormats = call('formats', formats);
for (const [name, format, extension] of [['photo', 'jpeg', 'jpg'], ['photo_alias', 'jpeg', 'jpg'], ['web', 'webp', 'webp']]) {
  assert.deepEqual(readFileSync(join(copiedFormats.output, 'media', `${copiedFormats.mapping[`example.R.drawable.${name}`]}.${extension}`)), Buffer.from(bitmaps[format], 'base64'));
}
// Independent decoder verifies genuine pixel streams, beyond production's file signatures.
const decode = spawnSync('python3', ['-B', '-c', `
import sys
from pathlib import Path
from PIL import Image
for directory in sys.argv[1:]:
    for path in Path(directory).iterdir():
        if path.suffix == '.svg': continue
        with Image.open(path) as image:
            image.load()
            assert image.size == (1, 1), path
print('PASS independently decoded PNG/JPEG/WebP pixels')
`, join(first.output, 'media'), join(copiedFormats.output, 'media')], { encoding: 'utf8', timeout: 10000 });
writeFileSync(join(work, 'bitmap-decode.json'), JSON.stringify({ status: decode.status, stdout: decode.stdout, stderr: decode.stderr }, null, 2));
assert.equal(decode.status, 0, decode.stderr);
assert.equal(call('repeat', res).properties, first.properties);
const other = call('namespace', res, 'other.example');
assert.ok(Object.values(other.mapping).every(value => !Object.values(first.mapping).includes(value)));
const before = readFileSync(join(first.output, 'image-resources.properties'));
call('existing', res, 'example', first.output, /already exists/);
assert.deepEqual(readFileSync(join(first.output, 'image-resources.properties')), before);
let negatives = 1;
function reject(label, entries, pattern) {
  const directory = join(work, `${label}-res`);
  mkdirSync(directory);
  for (const [name, payload] of entries) resource(directory, name, payload);
  const output = call(label, directory, 'example', join(work, label), pattern);
  assert.equal(existsSync(output), false, 'Failure must not publish an output directory');
  assert.equal(readdirSync(work).some(name => name.startsWith(`.${label}-stage-`)), false);
  negatives++;
}
reject('duplicate', [['drawable/a.png', png], ['drawable-nodpi/a.png', png]], /Ambiguous.*example.R.drawable.a/);
reject('qualified', [['drawable/a.png', png], ['drawable-hdpi/a.png', png]], /qualified.*drawable-hdpi/);
reject('qualified-only', [['drawable-night/a.png', png]], /qualified.*drawable-night/);
reject('nine-patch', [['drawable/a.9.png', png]], /9.patch/);
reject('selector', [['drawable/a.xml', '<selector/>']], /not an Android vector/);
reject('theme', [['drawable/a.png', png], ['drawable/z.xml', readFileSync(join(here, 'fixtures/theme.xml'))]], /tint|theme/);
reject('mirrored', [['drawable/a.xml', readFileSync(join(here, 'fixtures/mirrored.xml'))]], /mirroring/);
reject('color-reference', [['drawable/a.xml', readFileSync(join(here, 'fixtures/static.xml'), 'utf8').replace('#FF336699', '@color/brand')]], /unresolved/);
reject('malformed', [['drawable/a.xml', '<vector']], /malformed/);
reject('unsupported-svg-input', [['drawable/a.svg', '<svg/>']], /Unsupported.*svg/);
reject('corrupt-png', [['drawable/a.png', 'not a PNG']], /PNG/);
reject('empty', [], /No supported drawable/);
call('bad-namespace', res, 'example\nmalicious', join(work, 'bad-namespace'), /namespace/);
assert.equal(existsSync(join(work, 'bad-namespace')), false);
negatives++;
const links = join(work, 'links-res');
mkdirSync(join(links, 'drawable'), { recursive: true });
symlinkSync(join(res, 'drawable/banner.png'), join(links, 'drawable/linked.png'));
call('symlink', links, 'example', join(work, 'symlink'), /symlink/);
assert.equal(existsSync(join(work, 'symlink')), false);
negatives++;
writeFileSync(join(work, 'complete.json'), JSON.stringify({ symbols: 3, repeatedBytesAndNames: true,
  bitmapFormats: ['png', 'jpg', 'jpeg', 'webp'], independentlyDecoded: true,
  namespaceIsolation: true, negativeCases: negatives, noJvmOrSdk: true,
  scriptSha256: createHash('sha256').update(readFileSync(script)).digest('hex') }, null, 2));
console.log(`PASS three materialized symbols, stable names/bytes, namespace separation and ${negatives} closed boundaries`);
