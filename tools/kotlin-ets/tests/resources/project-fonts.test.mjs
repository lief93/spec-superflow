import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { materializeProjectFonts } from '../../font-resources.mjs';

function write(path, bytes) {
  mkdirSync(join(path, '..'), { recursive: true });
  writeFileSync(path, bytes);
}

test('selected variant materializes local fonts with source-set overlays', () => {
  const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-project-fonts-'));
  const main = join(work, 'main-res');
  const debug = join(work, 'debug-res');
  write(join(main, 'font/regular.ttf'), Buffer.from('main'));
  write(join(main, 'font/medium.otf'), Buffer.from('medium'));
  write(join(debug, 'font/regular.ttf'), Buffer.from('debug'));
  write(join(main, 'font/family.xml'), Buffer.from('<font-family/>'));
  const symbols = join(work, 'R.txt');
  writeFileSync(symbols, [
    'int font regular 0x7f010001',
    'int font medium 0x7f010002',
    'int font family 0x7f010003',
    'int font missing 0x7f010004',
  ].join('\n') + '\n');
  const pack = materializeProjectFonts({ namespace: 'sample.app', variant: 'debug', symbolsFile: symbols,
    resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: main },
      { sourceSet: 'debug', overlayPriority: 1, path: debug }], out: join(work, 'out') });
  assert.equal(pack.count, 2);
  assert.equal(pack.unsupportedCount, 2);
  const properties = readFileSync(pack.properties, 'utf8');
  const regular = /^sample\.app\.R\.font\.regular=(.+)$/m.exec(properties)[1];
  assert.equal(readFileSync(join(pack.output, regular), 'utf8'), 'debug');
  const origins = JSON.parse(readFileSync(pack.provenance, 'utf8'));
  const selected = origins.resources.find(resource => resource.symbol === 'sample.app.R.font.regular');
  assert.equal(selected.source.sourceSet, 'debug');
  assert.equal(selected.shadowed[0].sourceSet, 'main');
  assert.match(origins.resources.find(resource => resource.symbol === 'sample.app.R.font.family').reason, /format/);
  assert.match(origins.resources.find(resource => resource.symbol === 'sample.app.R.font.missing').reason, /No .* file/);
});

test('same-priority duplicate font definitions fail without publishing output', () => {
  const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-project-font-duplicate-'));
  const first = join(work, 'first');
  const second = join(work, 'second');
  write(join(first, 'font/regular.ttf'), Buffer.from('first'));
  write(join(second, 'font/regular.otf'), Buffer.from('second'));
  const symbols = join(work, 'R.txt');
  writeFileSync(symbols, 'int font regular 0x7f010001\n');
  const output = join(work, 'out');
  assert.throws(() => materializeProjectFonts({ namespace: 'sample', variant: 'debug', symbolsFile: symbols,
    resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: first },
      { sourceSet: 'main', overlayPriority: 0, path: second }], out: output }), /Ambiguous project font resource/);
  assert.equal(existsSync(output), false);
});
