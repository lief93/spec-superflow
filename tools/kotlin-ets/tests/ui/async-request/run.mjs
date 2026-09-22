import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { materializeImages } from '../../../image-resources.mjs';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-async-request-'));
console.log(`Evidence: ${work}`);
assert.ok(process.argv[2], 'Supply a Compose/Coil classpath file');
const res = join(work, 'res'); mkdirSync(join(res, 'drawable'), { recursive: true });
writeFileSync(join(res, 'drawable/logo.xml'), '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="16dp" android:height="16dp" android:viewportWidth="16" android:viewportHeight="16"><path android:fillColor="#00FF00" android:pathData="M0,0H16V16H0Z"/></vector>');
const symbols = join(work, 'R.txt'); writeFileSync(symbols, 'int drawable logo 0x7f080001\n');
const pack = materializeImages({ resDir: res, namespace: 'asyncimages', symbolsFile: symbols, out: join(work, 'pack') });
function run(label, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  return result.stdout;
}
const classes = join(work, 'classes'); mkdirSync(classes);
run('javac', '/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/javac', ['-d', classes, join(here, 'R.java')]);
const cp = join(work, 'classpath.txt'); writeFileSync(cp, classes + '\n' + readFileSync(process.argv[2], 'utf8'));
const common = [join(root, 'kotlin-ets'), '--mode', 'page', '--classpath-file', cp, '--image-resources', pack.properties];
const out = join(work, 'Page.ets');
run('page', 'bash', [...common, '--entry', 'asyncimages.Page', '--out', out, join(here, 'Page.kt')]);
const source = readFileSync(out, 'utf8');
assert.match(source, /EtsAsyncImage\(\{ request: new EtsImageRequest\(url\.value/);
assert.match(source, /Picture\(__etsMaterialContext: EtsMaterialContext, url: Binding<string \| null>\)/);
assert.match(source, /UIUtils\.makeBinding/);
assert.match(source, /function inspectionPlaceholder\(id: number\)/);
assert.match(source, /false \? __etsPainterResource\(id\) : null/);

// Exercise emitted lifecycle methods, without simulating native rendering or network IO.
const parsed = ts.createSourceFile('page.ts', source.replaceAll('export struct ', 'export class '), ts.ScriptTarget.ES2022, true);
const printer = ts.createPrinter();
const declarations = parsed.statements.filter(node => ts.isClassDeclaration(node) &&
  ['EtsAsyncImage', 'EtsImageRequest', 'EtsImageRequestBuilder', 'EtsSvgDecoder'].includes(node.name?.text));
assert.equal(declarations.length, 4);
const ordinary = declarations.map(node => printer.printNode(ts.EmitHint.Unspecified,
  ts.factory.updateClassDeclaration(node, [ts.factory.createModifier(ts.SyntaxKind.ExportKeyword)], node.name,
    node.typeParameters, node.heritageClauses, node.members.filter(member => member.name?.getText(parsed) !== 'build')
      .map(member => ts.isPropertyDeclaration(member) ? ts.factory.updatePropertyDeclaration(member,
        member.modifiers?.filter(modifier => modifier.kind !== ts.SyntaxKind.Decorator), member.name,
        member.questionToken ?? member.exclamationToken, member.type, member.initializer) : member)), parsed)).join('\n');
const animations = [];
const context = vm.createContext({ exports: {}, ImageFit: { Contain: 0 }, Curve: { Linear: 0 },
  animateTo: (options, update) => { animations.push(options); update(); } });
vm.runInContext(ts.transpileModule(ordinary, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
const { EtsAsyncImage, EtsImageRequest } = context.exports;
const image = new EtsAsyncImage();
image.request = new EtsImageRequest('a.svg', 600, null); image.aboutToAppear();
const first = image.generation;
assert.deepEqual(Array.from(image.tokens), [first]);
assert.equal(image.showPlaceholder, true); assert.equal(image.progress, 0);
image.loaded(first); assert.equal(image.progress, 1); assert.equal(image.showPlaceholder, true);
assert.equal(animations.length, 1); assert.equal(animations[0].duration, 600);
image.loaded(first); assert.equal(animations.length, 1);
image.request = new EtsImageRequest('b.svg', 200, null); image.requestChanged();
const second = image.generation;
assert.notEqual(first, second); assert.equal(image.progress, 0);
animations[0].onFinish(); image.failed(first); image.loaded(first);
assert.equal(image.showPlaceholder, true); assert.equal(image.progress, 0); assert.equal(animations.length, 1);
image.loaded(second); animations[1].onFinish(); assert.equal(image.showPlaceholder, false);
image.request = new EtsImageRequest('b.svg', 200, null); image.requestChanged();
assert.equal(image.generation, second, 'Equivalent rebuilt descriptor must not reset loaded image');
image.request = new EtsImageRequest('c.svg', 0, null); image.requestChanged(); image.failed(image.generation);
assert.equal(image.showPlaceholder, false); assert.equal(image.progress, 0);
image.request = new EtsImageRequest(null, 0, null); image.requestChanged();
assert.equal(image.tokens.length, 0); assert.equal(image.showPlaceholder, false);
image.request = new EtsImageRequest('d.svg', 0, null); image.requestChanged(); image.loaded(image.generation);
assert.equal(image.progress, 1); assert.equal(image.showPlaceholder, false);
image.request = new EtsImageRequest('e.svg', 100, null); image.requestChanged();
const disposed = image.generation; image.aboutToDisappear(); image.loaded(disposed); image.failed(disposed);
assert.equal(image.progress, 0); assert.equal(animations.length, 2);
writeFileSync(join(work, 'state-result.json'), JSON.stringify({ passed: true, animationDurations: animations.map(x => x.duration) }));
for (const [entry, message] of [['Unbounded', /requires bounded width and height/], ['UnsupportedCallback', /argument: onSuccess/],
  ['UnsafeArgument', /evaluation-preserving composition boundary/]]) {
  const destination = join(work, entry + '.ets');
  assert.match(run(entry, 'bash', [...common, '--entry', 'asyncimages.' + entry, '--out', destination, join(here, 'Page.kt')], 2), message);
  assert.equal(existsSync(destination), false);
}
console.log('PASS emitted request lifecycle, placeholders, durations, stale callbacks, null/error and explicit unsupported paths');
