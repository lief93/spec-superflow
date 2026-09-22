import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { compilerCompatibility, compilerEnvironment } from '../../compiler-environment.mjs';

const dir = mkdtempSync(join(tmpdir(), 'compiler plugins '));
const jar = name => { const path = join(dir, name); writeFileSync(path, 'test path'); return path; };
const serialization = jar('kotlin-serialization-compiler-plugin-embeddable-2.1.20.jar');
const serialization210 = jar('kotlin-serialization-compiler-plugin-embeddable-2.1.0.jar');
test('forwards serialization and semantic options, isolates JVM destinations', () => {
  const option = 'plugin:org.jetbrains.kotlinx.serialization:disableIntrinsic=true';
  const result = compilerEnvironment({ compilerVersion: '2.1.20', compilerArguments: [
    '-d', '/do not write/classes', '-jvm-target', '17', '-language-version', '2.1',
    '-Xplugin=' + serialization, '-P', option, '-opt-in=sample.Experimental', '-Xjvm-default=all',
  ] });
  assert.deepEqual(result.arguments, ['-jvm-target', '17', '-language-version', '2.1',
    '-Xplugin=' + serialization, '-P', option, '-opt-in=sample.Experimental', '-Xjvm-default=all']);
  assert.ok(result.excluded.some(x => x.argument === '-d=/do not write/classes'));
});
test('records Compose ownership and excludes scripting for kt/java-only input', () => {
  const compose = jar('kotlin-compose-compiler-plugin-embeddable-2.1.20.jar');
  const scripting = jar('kotlin-scripting-compiler-embeddable-2.1.20.jar');
  const result = compilerEnvironment({ compilerVersion: '2.1.20', compilerArguments: [
    `-Xplugin=${serialization},${compose},${scripting}`, '-P', 'plugin:androidx.compose.compiler.plugins.kotlin:sourceInformation=true',
  ] });
  assert.deepEqual(result.arguments, ['-Xplugin=' + serialization]);
  assert.ok(result.excluded.some(x => x.reason.includes('ArkUI')));
  assert.ok(result.excluded.some(x => x.reason.includes('scripts')));
});
test('accepts an older patch on the same Kotlin language line and records the decision', () => {
  const compose = jar('kotlin-compose-compiler-plugin-embeddable-2.1.0.jar');
  const result = compilerEnvironment({ compilerVersion: '2.1.0', compilerArguments: [
    `-Xplugin=${serialization210},${compose}`, '-P', 'plugin:org.jetbrains.kotlinx.serialization:disableIntrinsic=true',
    '-Xallow-unstable-dependencies',
  ] });
  assert.equal(result.projectCompilerVersion, '2.1.0');
  assert.equal(result.frontendCompilerVersion, '2.1.20');
  assert.equal(result.compatibilityDecision, 'same_language_line_older_patch');
  assert.deepEqual(result.arguments, []);
  assert.ok(result.excluded.some(x => x.argument === compose && x.reason.includes('ArkUI')));
  assert.ok(result.excluded.some(x => x.argument === serialization210 && x.reason.includes('not loaded')));
  assert.ok(result.excluded.some(x => x.argument.includes('org.jetbrains.kotlinx.serialization') && x.reason.includes('options')));
  assert.ok(result.excluded.some(x => x.argument === '-Xallow-unstable-dependencies' && x.reason.includes('does not relax')));
});

test('rejects incompatible compiler lines, newer patches, unstable labels, arguments and missing artifacts', () => {
  const coupled = jar('custom-compiler-plugin-2.1.0.jar');
  for (const version of ['2.0.20', '2.2.0', '2.1.21', '2.1.20-RC1', '', undefined])
    assert.throws(() => compilerCompatibility(version), /Kotlin|compiler|version|patch/i);
  for (const input of [
    { compilerVersion: '2.1.20', compilerArguments: ['-Xplugin=' + join(dir, 'missing.jar')] },
    { compilerVersion: '2.1.20', compilerArguments: ['-Xsomething-new=true'] },
    { compilerVersion: '2.1.20', compilerArguments: ['-language-version'] },
    { compilerVersion: '2.1.0', compilerArguments: ['-Xplugin=' + coupled] },
  ]) assert.throws(() => compilerEnvironment(input));
});

test('preserves plugin classloader dependencies and delegates option ownership to Kotlin', () => {
  const implementation = jar('example-processor.jar');
  const dependency = jar('helper-library.jar');
  const classpath = `-Xplugin=${implementation},${dependency},${serialization}`;
  const option = 'plugin:example.processor:mode=normal';
  const result = compilerEnvironment({ compilerVersion: '2.1.20', compilerArguments: [classpath, '-P', option] });
  assert.deepEqual(result.arguments, [classpath, '-P', option]);
  assert.deepEqual(result.excluded, []);
});

test('keeps serialization options when Gradle serializes mixed plugin options in one token', () => {
  const result = compilerEnvironment({ compilerVersion: '2.1.20', compilerArguments: ['-no-jdk', '-Xallow-unstable-dependencies',
    `-Xplugin=${serialization}`, '-P', 'plugin:androidx.compose.compiler.plugins.kotlin:sourceInformation=true,' +
    'plugin:org.jetbrains.kotlinx.serialization:disableIntrinsic=true'] });
  assert.deepEqual(result.arguments, ['-no-jdk', `-Xplugin=${serialization}`,
    '-P', 'plugin:org.jetbrains.kotlinx.serialization:disableIntrinsic=true']);
  assert.ok(result.excluded.some(x => x.argument === '-Xallow-unstable-dependencies'));
});
