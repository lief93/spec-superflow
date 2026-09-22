import { readFileSync, statSync } from 'node:fs';
import { basename, isAbsolute } from 'node:path';

export const frontendCompilerVersion = '2.1.20';
const composeId = 'androidx.compose.compiler.plugins.kotlin';
const serializationId = 'org.jetbrains.kotlinx.serialization';
const valued = new Set(['-language-version', '-api-version', '-jvm-target', '-module-name', '-opt-in',
  '-jdk-home', '-Xjvm-default', '-Xjsr305', '-Xjdk-release', '-Xnullability-annotations', '-Xfriend-paths']);
const flags = new Set(['-no-stdlib', '-no-reflect', '-no-jdk', '-java-parameters', '-progressive', '-nowarn', '-Werror',
  '-Xcontext-receivers', '-Xemit-jvm-type-annotations', '-Xjspecify-annotations=strict']);
const buildValues = new Set(['-d', '-classpath', '-cp']);
const buildFlags = new Set(['-Xallow-no-source-files', '-Xuse-inline-scopes-numbers']);
const pluginServices = [
  'META-INF/services/org.jetbrains.kotlin.compiler.plugin.CompilerPluginRegistrar',
  'META-INF/services/org.jetbrains.kotlin.compiler.plugin.ComponentRegistrar',
  'META-INF/services/org.jetbrains.kotlin.compiler.plugin.CommandLineProcessor',
].map(value => Buffer.from(value));

function declaresCompilerPlugin(path) {
  const archive = readFileSync(path);
  return pluginServices.some(service => archive.includes(service));
}

// This is a compiler-environment boundary, not language/API name rewriting.
// Record every intentional exclusion; unknown semantic inputs fail closed.
export function compilerCompatibility(projectCompilerVersion) {
  const parse = (value, label) => {
    if (typeof value !== 'string' || !/^\d+\.\d+\.\d+$/.test(value))
      throw new Error(`${label} must be a stable numeric Kotlin version (major.minor.patch): ${value ?? 'missing'}`);
    return value.split('.').map(Number);
  };
  const project = parse(projectCompilerVersion, 'Project compiler version');
  const frontend = parse(frontendCompilerVersion, 'ETS frontend compiler version');
  if (project[0] !== frontend[0] || project[1] !== frontend[1]) {
    throw new Error(`Incompatible Kotlin compiler line: project ${projectCompilerVersion}, ETS frontend ${frontendCompilerVersion}; ` +
      'the project major/minor must match the frontend');
  }
  if (project[2] > frontend[2]) {
    throw new Error(`Incompatible newer Kotlin patch: project ${projectCompilerVersion}, ETS frontend ${frontendCompilerVersion}`);
  }
  return project[2] === frontend[2] ? 'exact_frontend_version' : 'same_language_line_older_patch';
}

export function compilerEnvironment(inputs) {
  const compatibilityDecision = compilerCompatibility(inputs.compilerVersion);
  const source = inputs.compilerArguments ?? [];
  if (!Array.isArray(source) || source.some(x => typeof x !== 'string' || !x || /[\r\n]/.test(x))) {
    throw new Error('Invalid serialized compiler arguments');
  }
  const result = { projectCompilerVersion: inputs.compilerVersion, frontendCompilerVersion,
    compatibilityDecision, arguments: [], excluded: [] };
  const exclude = (argument, reason) => result.excluded.push({ argument, reason });
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
      const retained = [];
      for (const path of paths) {
        if (!isAbsolute(path) || !statSync(path).isFile()) throw new Error(`Invalid compiler plugin path: ${path}`);
        const name = basename(path);
        if (/^kotlin-compose-compiler-plugin-embeddable-\d+\.\d+\.\d+(?:[-.][A-Za-z0-9.-]+)?\.jar$/.test(name)) {
          exclude(path, 'Compose source UI is lowered by the ArkUI backend, not JVM Compose lowering');
        } else if (/^kotlin-scripting-(?:compiler(?:-impl)?-embeddable)-\d+\.\d+\.\d+(?:[-.][A-Za-z0-9.-]+)?\.jar$/.test(name)) {
          exclude(path, 'Gradle scripting support; input collection admits kt/java files, not scripts');
        } else {
          const serialization = name.match(/^kotlin-serialization-compiler-plugin-embeddable-(\d+\.\d+\.\d+)\.jar$/);
          const versioned = name.match(/-(\d+\.\d+\.\d+)\.jar$/);
          if (serialization && serialization[1] !== frontendCompilerVersion) {
            exclude(path, 'Older serialization compiler codegen is not loaded into the fixed frontend; generated serializer references must resolve without it or source analysis fails');
          } else if (versioned && declaresCompilerPlugin(path) &&
            versioned[1] === inputs.compilerVersion && versioned[1] !== frontendCompilerVersion) {
            throw new Error(`Incompatible compiler plugin ${name}: project plugin ${versioned[1]}, ETS frontend ${frontendCompilerVersion}`);
          } else retained.push(path);
        }
      }
      // -Xplugin is a classloader path, including ordinary dependencies. Kotlin's
      // service loader, not artifact filenames, identifies implementations.
      if (retained.length) result.arguments.push(`-Xplugin=${retained.join(',')}`);
    } else if (key === '-P') {
      // CommonCompilerArguments.pluginOptions uses the official comma delimiter.
      for (const option of value().split(',')) {
        if (option.startsWith(`plugin:${composeId}:`)) {
          exclude(option, 'Compose compiler option belongs to JVM Compose lowering; ArkUI backend owns UI conversion');
        } else if (compatibilityDecision === 'same_language_line_older_patch' &&
          option.startsWith(`plugin:${serializationId}:`)) {
          exclude(option, 'Serialization options require the excluded older compiler plugin');
        } else result.arguments.push('-P', option);
      }
    } else if (valued.has(key)) {
      const v = value(); result.arguments.push(...(equals < 0 ? [key, v] : [argument]));
    } else if (argument === '-Xallow-unstable-dependencies') {
      exclude(argument, 'ETS compatibility validation does not relax dependency metadata stability');
    } else if (flags.has(argument)) {
      result.arguments.push(argument);
    } else if (buildValues.has(key)) {
      exclude(`${key}=${value()}`, 'Destination/classpath is supplied by the ETS frontend entry');
    } else if (buildFlags.has(argument)) {
      exclude(argument, 'JVM task/output option; ETS entry owns source validation and target output');
    } else throw new Error(`Unsupported compiler argument: ${argument}; not silently discarded`);
  }
  return result;
}
