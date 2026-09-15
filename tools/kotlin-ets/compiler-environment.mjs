import { statSync } from 'node:fs';
import { basename, isAbsolute } from 'node:path';

const version = '2.1.20';
const serializationId = 'org.jetbrains.kotlinx.serialization';
const composeId = 'androidx.compose.compiler.plugins.kotlin';
const valued = new Set(['-language-version', '-api-version', '-jvm-target', '-module-name', '-opt-in',
  '-jdk-home', '-Xjvm-default', '-Xjsr305', '-Xjdk-release', '-Xnullability-annotations', '-Xfriend-paths']);
const flags = new Set(['-no-stdlib', '-no-reflect', '-no-jdk', '-java-parameters', '-progressive', '-nowarn', '-Werror',
  '-Xallow-unstable-dependencies',
  '-Xcontext-receivers', '-Xemit-jvm-type-annotations', '-Xjspecify-annotations=strict']);
const buildValues = new Set(['-d', '-classpath', '-cp']);
const buildFlags = new Set(['-Xallow-no-source-files', '-Xuse-inline-scopes-numbers']);

// This is a compiler-environment boundary, not language/API name rewriting.
// Record every intentional exclusion; unknown semantic inputs fail closed.
export function compilerEnvironment(inputs) {
  if (inputs.compilerVersion && inputs.compilerVersion !== version) {
    throw new Error(`Compiler environment requires Kotlin ${version}; project uses ${inputs.compilerVersion}`);
  }
  const source = inputs.compilerArguments ?? [];
  if (!Array.isArray(source) || source.some(x => typeof x !== 'string' || !x || /[\r\n]/.test(x))) {
    throw new Error('Invalid serialized compiler arguments');
  }
  const result = { compilerVersion: version, arguments: [], excluded: [] };
  const exclude = (argument, reason) => result.excluded.push({ argument, reason });
  let hasSerialization = false;
  let needsSerialization = false;
  for (let i = 0; i < source.length; i++) {
    const argument = source[i];
    const equals = argument.indexOf('=');
    const key = equals < 0 ? argument : argument.slice(0, equals);
    const value = () => {
      const v = equals < 0 ? source[++i] : argument.slice(equals + 1);
      if (!v || v.startsWith('-')) throw new Error(`Missing compiler argument value: ${key}`);
      return v;
    };
    if (key === '-Xplugin') {
      const paths = value().split(',');
      for (const path of paths) {
        if (!isAbsolute(path) || !statSync(path).isFile()) throw new Error(`Invalid compiler plugin path: ${path}`);
        const name = basename(path);
        if (name === `kotlin-serialization-compiler-plugin-embeddable-${version}.jar`) {
          result.arguments.push(`-Xplugin=${path}`); hasSerialization = true;
        } else if (name === `kotlin-compose-compiler-plugin-embeddable-${version}.jar`) {
          exclude(path, 'Compose source UI is lowered by the ArkUI backend, not JVM Compose lowering');
        } else if (new RegExp(`^kotlin-(?:scripting-(?:compiler(?:-impl)?-embeddable|jvm|common)|script-runtime|stdlib)-${version.replaceAll('.', '\\.')}\\.jar$`).test(name)
          || name === 'annotations-13.0.jar') {
          exclude(path, 'Gradle scripting support; input collection admits kt/java files, not scripts');
        } else throw new Error(`Unsupported compiler plugin artifact: ${path}; supported semantic plugin: serialization ${version}`);
      }
    } else if (key === '-P') {
      // CommonCompilerArguments.pluginOptions uses the official comma delimiter.
      for (const option of value().split(',')) {
        if (option.startsWith(`plugin:${serializationId}:`)) {
          result.arguments.push('-P', option); needsSerialization = true;
        } else if (option.startsWith(`plugin:${composeId}:`)) {
          exclude(option, 'Compose compiler option belongs to JVM Compose lowering; ArkUI backend owns UI conversion');
        } else throw new Error(`Unsupported compiler plugin option: ${option}`);
      }
    } else if (valued.has(key)) {
      const v = value(); result.arguments.push(...(equals < 0 ? [key, v] : [argument]));
    } else if (flags.has(argument)) {
      result.arguments.push(argument);
    } else if (buildValues.has(key)) {
      exclude(`${key}=${value()}`, 'Destination/classpath is supplied by the ETS frontend entry');
    } else if (buildFlags.has(argument)) {
      exclude(argument, 'JVM task/output option; ETS entry owns source validation and target output');
    } else throw new Error(`Unsupported compiler argument: ${argument}; not silently discarded`);
  }
  if (needsSerialization && !hasSerialization) throw new Error('Serialization options have no serialization compiler plugin artifact');
  return result;
}
