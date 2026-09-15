import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { compilerEnvironment } from '../../compiler-environment.mjs';

const dir = mkdtempSync(join(tmpdir(), 'compiler plugins '));
const jar = name => { const path = join(dir, name); writeFileSync(path, 'test path'); return path; };
const serialization = jar('kotlin-serialization-compiler-plugin-embeddable-2.1.20.jar');
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
test('rejects unsupported versions, arguments and missing plugin artifacts', () => {
  for (const input of [
    { compilerVersion: '2.0.0', compilerArguments: [] },
    { compilerArguments: ['-Xplugin=' + join(dir, 'missing.jar')] },
    { compilerArguments: ['-Xsomething-new=true'] },
    { compilerArguments: ['-language-version'] },
  ]) assert.throws(() => compilerEnvironment(input));
});

test('preserves plugin classloader dependencies and delegates option ownership to Kotlin', () => {
  const implementation = jar('example-processor.jar');
  const dependency = jar('helper-library.jar');
  const classpath = `-Xplugin=${implementation},${dependency},${serialization}`;
  const option = 'plugin:example.processor:mode=normal';
  const result = compilerEnvironment({ compilerArguments: [classpath, '-P', option] });
  assert.deepEqual(result.arguments, [classpath, '-P', option]);
  assert.deepEqual(result.excluded, []);
});

test('keeps serialization options when Gradle serializes mixed plugin options in one token', () => {
  const result = compilerEnvironment({ compilerArguments: ['-no-jdk', '-Xallow-unstable-dependencies',
    `-Xplugin=${serialization}`, '-P', 'plugin:androidx.compose.compiler.plugins.kotlin:sourceInformation=true,' +
    'plugin:org.jetbrains.kotlinx.serialization:disableIntrinsic=true'] });
  assert.deepEqual(result.arguments, ['-no-jdk', '-Xallow-unstable-dependencies', `-Xplugin=${serialization}`,
    '-P', 'plugin:org.jetbrains.kotlinx.serialization:disableIntrinsic=true']);
});
