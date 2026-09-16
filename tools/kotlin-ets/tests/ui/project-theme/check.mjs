import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const code = readFileSync(process.argv[2], 'utf8').replace('export struct Page', 'export class Page');
const parsed = ts.createSourceFile('page.ts', code, ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(n => !ts.isImportDeclaration(n) &&
  !(ts.isClassDeclaration(n) && n.name?.text === 'Page')).map(n => n.getFullText(parsed)).join('\n');
const modes = [];
const reads = [];
let primary = 0xff1256ab;
const hostConfiguration = {colorMode: 1, locale: 'en-US', screenDensity: 480};
const host = {resourceManager: {
  getConfigurationSync: () => ({...hostConfiguration}),
  getOverrideResourceManager(configuration) {
    modes.push(configuration.colorMode);
    assert.equal(configuration.locale, 'en-US');
    assert.equal(configuration.screenDensity, 480);
    return {getColorByNameSync(name) {
      assert.match(name, /^kotlin_ets_material_[a-z_]+$/);
      assert.doesNotMatch(name, /material_(light|dark)_/);
      reads.push(name);
      if (name === 'kotlin_ets_material_primary') return configuration.colorMode === 0 ? 0xffda3478 : primary;
      if (name === 'kotlin_ets_material_on_primary') return configuration.colorMode === 0 ? 0xff000000 : 0xffffffff;
      throw new Error('missing resource');
    }};
  },
}};
const context = vm.createContext({exports: {}, __etsResourceManager: {ColorMode: {DARK: 0, LIGHT: 1}}});
vm.runInContext(ts.transpileModule(ordinary, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}}).outputText, context);
const light = context.exports.palette(host, false);
const dark = context.exports.palette(host, true);
assert.equal(reads.length, 0, 'creating a palette must not require unused resources');
assert.equal(light.primary, 0xff1256ab);
assert.equal(light.onPrimary, 0xffffffff);
assert.equal(dark.primary, 0xffda3478);
assert.equal(dark.onPrimary, 0xff000000);
assert.equal(reads.length, 4, 'read only colors actually consumed');
assert.equal(new Set(reads).size, 2, 'both modes use the same resource names');
assert.deepEqual(modes, [1, 0]);
assert.equal(hostConfiguration.colorMode, 1, 'host configuration must not be mutated');
primary = 0xff224466;
assert.equal(light.primary, primary, 'existing palette does not cache color values');
assert.equal(context.exports.palette(host, false).primary, primary, 'subsequent calls must not cache resources');
const broken = {resourceManager: {...host.resourceManager, getOverrideResourceManager() {
  return {getColorByNameSync() {throw new Error('missing resource');}};
}}};
assert.throws(() => context.exports.palette(broken, false).primary, /kotlin_ets_material_primary.*missing resource/);
assert.throws(() => light.tertiary, /kotlin_ets_material_tertiary.*missing resource/);
console.log('PASS explicit palettes, shared names, configuration isolation, refresh and named failures');
