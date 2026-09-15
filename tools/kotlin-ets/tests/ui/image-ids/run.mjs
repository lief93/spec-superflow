import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { materializeImages } from '../../../image-resources.mjs';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-image-ids-'));
console.log(`Evidence: ${work}`);
const res = join(work, 'res'); mkdirSync(join(res, 'drawable'), { recursive: true });
const vector = '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="16dp" android:height="16dp" android:viewportWidth="16" android:viewportHeight="16"><path android:fillColor="#00FF00" android:pathData="M0,0H16V16H0Z"/></vector>';
for (const name of ['logo', 'second']) writeFileSync(join(res, 'drawable', name + '.xml'), vector);
writeFileSync(join(res, 'drawable', 'unused.xml'), '<selector/>');
const symbols = join(work, 'R.txt');
writeFileSync(symbols, 'int drawable logo 0x7f080001\nint drawable second 0x7f080002\n');
const pack = materializeImages({ resDir: res, namespace: 'imageids', out: join(work, 'pack'), symbolsFile: symbols, include: ['logo', 'second'] });
assert.match(readFileSync(join(pack.output, 'source-resource-ids.properties'), 'utf8'), /imageids.R.drawable.logo = 2131230721/);
assert.throws(() => materializeImages({ resDir: res, namespace: 'imageids', out: join(work, 'missing'), include: ['absent'] }), /missing/);
writeFileSync(symbols, 'int drawable logo 0x7f080001\nint drawable second 0x7f080001\n');
assert.throws(() => materializeImages({ resDir: res, namespace: 'imageids', out: join(work, 'ambiguous'), symbolsFile: symbols, include: ['logo', 'second'] }), /ambiguous/);
function run(name, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, name + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  return result.stdout;
}
const classes = join(work, 'classes'); mkdirSync(classes);
run('javac', '/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/javac', ['-d', classes, join(here, 'R.java')]);
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync);
writeFileSync(join(work, 'classpath.txt'), [classes, ...cp].join('\n'));
const out = join(work, 'Page.ets');
run('compile', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--entry', 'imageids.Page',
  '--classpath-file', join(work, 'classpath.txt'), '--image-resources', pack.properties, '--out', out, join(here, 'Page.kt')]);
const source = readFileSync(out, 'utf8');
assert.match(source, /retained\(2131230721\)/);
assert.match(source, /function icon\(id: number\)/);
const parsed = ts.createSourceFile('page.ts', source.replace('export struct Page', 'export class Page'), ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(node => !ts.isImportDeclaration(node) && !(ts.isClassDeclaration(node) && node.name?.text === 'Page'))
  .map(node => node.getFullText(parsed)).join('\n');
const context = vm.createContext({ exports: {}, $r: key => ({ key }) });
vm.runInContext(ts.transpileModule(ordinary, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
for (const id of [0x7f080001, 0x7f080002]) {
  assert.equal(context.exports.retained(id), id);
  assert.match(context.exports.icon(id).key, /^app.media.img_[0-9a-f]{64}$/);
}
assert.notEqual(context.exports.icon(0x7f080001).key, context.exports.icon(0x7f080002).key);
assert.deepEqual({ chosen: context.exports.chosen().key, effectful: context.exports.effectful().key,
  reads: context.exports.readCount() }, { chosen: context.exports.icon(0x7f080002).key,
  effectful: context.exports.icon(0x7f080001).key, reads: 1 });
assert.throws(() => context.exports.icon(123), { name: 'IllegalArgumentException' });
const media = join(out + '.resources', 'base/media');
assert.equal(readdirSync(media).length, 2);
for (const file of readdirSync(media)) assert.deepEqual(readFileSync(join(media, file)), readFileSync(join(pack.output, 'media', file)));
console.log('PASS actual Int resource IDs, ordinary parameter flow, dynamic painter lookup and exact media artifacts');
