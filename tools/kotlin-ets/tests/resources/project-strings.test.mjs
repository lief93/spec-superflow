import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { materializeProjectStrings } from '../../string-resources.mjs';

function write(path, text) {
  mkdirSync(join(path, '..'), { recursive: true });
  writeFileSync(path, text);
}

function decodedProperties(path) {
  return new Map(readFileSync(path, 'utf8').trim().split('\n').filter(Boolean).map(line => {
    const split = line.indexOf('=');
    return [line.slice(0, split), line.slice(split + 1)];
  }));
}

test('selected variant materializes string, plurals and arrays with overlays and explicit failures', () => {
  const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-project-strings-'));
  const main = join(work, 'main-res');
  const debug = join(work, 'debug-res');
  write(join(main, 'values/strings.xml'), `<resources>
    <string name="greeting">Hello %1$s: %2$d</string>
    <string name="escaped">"  A &amp; B\\n\\"quoted\\""</string>
    <string name="styled"><b>Bold</b></string>
    <string name="icu">{count, plural, one {One} other {Many}}</string>
    <string name="regional">Default</string>
    <plurals name="photos"><item quantity="one">%1$d photo</item><item quantity="other">%1$d photos</item></plurals>
    <string-array name="labels"><item>First</item><item>Second &amp; last</item></string-array>
  </resources>`);
  write(join(main, 'values-fr/strings.xml'), '<resources><string name="greeting">Bonjour %1$s : %2$d</string></resources>');
  write(join(main, 'values-b+zh+Hant/strings.xml'), '<resources><string name="regional">繁體</string></resources>');
  write(join(debug, 'values/strings.xml'), `<resources>
    <string name="greeting">Debug %1$s: %2$d</string>
    <plurals name="photos"><item quantity="one">%1$d debug photo</item><item quantity="other">%1$d debug photos</item></plurals>
  </resources>`);
  const symbols = join(work, 'R.txt');
  writeFileSync(symbols, [
    'int string greeting 0x7f010001', 'int string escaped 0x7f010002', 'int string styled 0x7f010003',
    'int string icu 0x7f010004', 'int string missing 0x7f010005', 'int string regional 0x7f010006', 'int plurals photos 0x7f020001',
    'int array labels 0x7f030001',
  ].join('\n') + '\n');
  const pack = materializeProjectStrings({ namespace: 'sample.app', variant: 'debug', symbolsFile: symbols,
    resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: main },
      { sourceSet: 'debug', overlayPriority: 1, path: debug }], out: join(work, 'out') });
  assert.equal(pack.count, 4);
  assert.equal(pack.unsupportedCount, 4);
  const base = readFileSync(join(pack.output, 'base.properties'), 'utf8');
  assert.match(base, /sample\.app\.R\.string\.greeting=Debug %1\$s\\: %2\$d/);
  assert.match(base, /sample\.app\.R\.string\.escaped=\\  A & B\\n"quoted"/);
  assert.match(readFileSync(join(pack.output, 'fr.properties'), 'utf8'), /Bonjour %1\$s/);
  assert.match(readFileSync(join(pack.output, 'plurals-base.properties'), 'utf8'), /debug photos/);
  assert.match(readFileSync(join(pack.output, 'arrays-base.properties'), 'utf8'), /Second & last/);
  const unsupported = decodedProperties(join(pack.output, 'unsupported-string-resources.properties'));
  assert.match(Buffer.from(unsupported.get('sample.app.R.string.styled'), 'base64').toString(), /styled spans/);
  assert.match(Buffer.from(unsupported.get('sample.app.R.string.icu'), 'base64').toString(), /complex ICU/);
  assert.match(Buffer.from(unsupported.get('sample.app.R.string.missing'), 'base64').toString(), /No default/);
  assert.match(Buffer.from(unsupported.get('sample.app.R.string.regional'), 'base64').toString(), /unsupported values qualifier/);
  const origins = JSON.parse(readFileSync(pack.provenance, 'utf8'));
  const greeting = origins.resources.find(resource => resource.symbol === 'sample.app.R.string.greeting');
  assert.equal(greeting.status, 'materialized');
  assert.equal(greeting.variants.find(item => item.qualifier === 'base').source.sourceSet, 'debug');
  assert.equal(greeting.variants.find(item => item.qualifier === 'base').shadowed[0].sourceSet, 'main');
});

test('same-priority duplicate values names fail without publishing output', () => {
  const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-project-string-duplicate-'));
  const first = join(work, 'first');
  const second = join(work, 'second');
  write(join(first, 'values/one.xml'), '<resources><string name="label">One</string></resources>');
  write(join(second, 'values/two.xml'), '<resources><string name="label">Two</string></resources>');
  const symbols = join(work, 'R.txt');
  writeFileSync(symbols, 'int string label 0x7f010001\n');
  assert.throws(() => materializeProjectStrings({ namespace: 'sample', variant: 'debug', symbolsFile: symbols,
    resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: first },
      { sourceSet: 'main', overlayPriority: 0, path: second }], out: join(work, 'out') }), /Ambiguous project string resource/);
});

test('library placeholder IDs retain named resources without inventing runtime IDs', () => {
  const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-project-string-library-'));
  const main = join(work, 'main-res');
  write(join(main, 'values/strings.xml'), '<resources><string name="label">Library</string></resources>');
  const symbols = join(work, 'R.txt');
  writeFileSync(symbols, 'int string label 0x0\n');
  const pack = materializeProjectStrings({ namespace: 'sample.library', variant: 'debug', symbolsFile: symbols,
    resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: main }], out: join(work, 'out') });
  assert.equal(pack.count, 1);
  assert.match(readFileSync(join(pack.output, 'base.properties'), 'utf8'), /sample\.library\.R\.string\.label=Library/);
  assert.equal(readFileSync(join(pack.output, 'source-resource-ids.properties'), 'utf8'), '');
});

test('selected dimensions retain base dp values and record unavailable qualifiers', () => {
  const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-project-dimensions-'));
  const main = join(work, 'main-res');
  write(join(main, 'values/dimens.xml'), `<resources>
    <dimen name="horizontal_margin">16dp</dimen>
    <string name="percentage">%1$.1f%%</string>
  </resources>`);
  write(join(main, 'values-w820dp/dimens.xml'),
    '<resources><dimen name="horizontal_margin">24dp</dimen></resources>');
  const symbols = join(work, 'R.txt');
  writeFileSync(symbols, [
    'int dimen horizontal_margin 0x7f040001',
    'int string percentage 0x7f010001',
  ].join('\n') + '\n');
  const pack = materializeProjectStrings({ namespace: 'sample.app', variant: 'debug', symbolsFile: symbols,
    resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: main }], out: join(work, 'out') });
  assert.equal(pack.count, 2);
  assert.equal(pack.unsupportedCount, 0);
  assert.equal(readFileSync(join(pack.output, 'dimensions.properties'), 'utf8'),
    'sample.app.R.dimen.horizontal_margin=16\n');
  assert.equal(readFileSync(join(pack.output, 'dimension-qualifiers.properties'), 'utf8'),
    'sample.app.R.dimen.horizontal_margin=w820dp\n');
  assert.match(readFileSync(join(pack.output, 'base.properties'), 'utf8'), /%1\$\.1f%%/);
  assert.match(readFileSync(join(pack.output, 'source-resource-ids.properties'), 'utf8'),
    /sample\.app\.R\.dimen\.horizontal_margin=2130968577/);
});
