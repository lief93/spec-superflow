import { spawnSync } from 'node:child_process';
import { closeSync, existsSync, lstatSync, mkdirSync, mkdtempSync, openSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compilerEnvironment } from './compiler-environment.mjs';
import { materializeProjectImages } from './image-resources.mjs';
import { materializeProjectStrings } from './string-resources.mjs';
import { materializeProjectFonts } from './font-resources.mjs';

const root = dirname(fileURLToPath(import.meta.url));
const help = `Kotlin to ETS: Gradle project input
bash tools/kotlin-ets/kotlin-ets --project /path/to/android --module :app \\
  --variant debug --entry sample.Page --out /path/to/new/Page.ets

--compile-task compileKotlin   Use an exact local task instead of --variant
--mode language               Translate ordinary Kotlin instead of a page
--unsupported-policy error    Strict conversion; default report allows only explicit animation/system projections, never unknown UI omissions
--out-dir /path/to/new/modules Output separate ETS source modules instead of --out
--collect-only                Collect inputs without running the ETS backend
--work-dir /path/to/new/run    Fresh directory for input lists and command logs
--offline                     Ask Gradle to use cached dependencies only
--dependency-sources-file /path/sources.txt  Explicit dependency Kotlin/Java sources, one absolute path per line
--image-resources /path/image-resources.properties  Use materialized image resources
--string-resources /path/string-inputs  Use materialized string inputs; emit sibling .resources bundle
--font-resources /path/font-inputs/fonts.properties  Use materialized local font files
--preflight-out /path/core-profile.json  Write the resolved Core Profile before target generation

Uses the project's Gradle wrapper and compile prerequisites. It does not edit
build scripts, compile the selected Kotlin task, install an app or upload files.
Node.js 18+ and the backend's cached compiler dependencies are required.
`;

export function parseOptions(args) {
  const values = new Map();
  const flags = new Set(['--offline', '--collect-only']);
  const options = new Set(['--project', '--module', '--variant', '--compile-task', '--mode', '--entry', '--out', '--out-dir', '--work-dir', '--image-resources', '--string-resources', '--font-resources', '--unsupported-policy', '--dependency-sources-file', '--preflight-out']);
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    if (!flags.has(key) && !options.has(key)) throw new Error(`Unknown project option: ${key}`);
    if (values.has(key)) throw new Error(`Duplicate option: ${key}`);
    const value = flags.has(key) ? true : args[++i];
    if (value === undefined || value === '' || typeof value === 'string' && value.startsWith('--')) throw new Error(`Missing value for ${key}`);
    values.set(key, value);
  }
  const get = key => values.get(`--${key}`);
  if (!get('project') || !get('module')) throw new Error('--project and --module are required');
  if (!/^:(?:[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)*)?$/.test(get('module'))) throw new Error('Use an absolute Gradle module path, for example :app');
  if (Boolean(get('variant')) === Boolean(get('compile-task'))) throw new Error('Specify exactly one of --variant or --compile-task');
  const variant = get('variant');
  if (variant && !/^[A-Za-z][A-Za-z0-9_]*$/.test(variant)) throw new Error('Invalid variant name');
  const compileTask = get('compile-task') || `compile${variant[0].toUpperCase()}${variant.slice(1)}Kotlin`;
  if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(compileTask)) throw new Error('Use a local Kotlin compile task name without a module prefix');
  const mode = get('mode') || 'page';
  if (!['page', 'language'].includes(mode)) throw new Error('Mode must be page or language');
  const unsupportedPolicy = get('unsupported-policy') || (mode === 'page' ? 'report' : 'error');
  if (!['report', 'error'].includes(unsupportedPolicy) || mode === 'language' && unsupportedPolicy !== 'error')
    throw new Error('Unsupported policy must be report or error; language mode requires error');
  if (get('out') && get('out-dir')) throw new Error('Specify only one of --out or --out-dir');
  if (!get('collect-only')) {
    if (!get('out') && !get('out-dir')) throw new Error('--out or --out-dir is required');
    if (mode === 'page' && !get('entry')) throw new Error('--entry is required for page mode');
  }
  const output = get('out') || get('out-dir') ? resolve(get('out') || get('out-dir')) : undefined;
  const preflightOutput = get('preflight-out') ? resolve(get('preflight-out')) : undefined;
  if (preflightOutput && (preflightOutput === output || (get('out-dir') && preflightOutput.startsWith(output + '/'))))
    throw new Error(`Preflight report must be outside the target path: ${preflightOutput}`);
  return { project: resolve(get('project')), module: get('module'), variant, compileTask, mode, unsupportedPolicy,
    entry: get('entry'), output,
    outputFlag: get('out-dir') ? '--out-dir' : '--out', workDir: get('work-dir') ? resolve(get('work-dir')) : undefined,
    imageResources: get('image-resources') ? resolve(get('image-resources')) : undefined,
    stringResources: get('string-resources') ? resolve(get('string-resources')) : undefined,
    fontResources: get('font-resources') ? resolve(get('font-resources')) : undefined,
    preflightOutput,
    dependencySourcesFile: get('dependency-sources-file') ? resolve(get('dependency-sources-file')) : undefined,
    offline: !!get('offline'), collectOnly: !!get('collect-only') };
}

export function gradleArguments(options, manifest) {
  const collectionTask = options.module === ':' ? ':kotlinEtsCollectInputs' : `${options.module}:kotlinEtsCollectInputs`;
  return [join(options.project, 'gradlew'), '--no-daemon', '--no-configuration-cache', '--console=plain',
    ...(options.offline ? ['--offline'] : []), '-I', join(root, 'project-inputs.gradle'),
    `-PkotlinEtsModule=${options.module}`, `-PkotlinEtsCompileTask=${options.compileTask}`,
    ...(options.variant ? [`-PkotlinEtsVariant=${options.variant}`] : []),
    `-PkotlinEtsInputsOutput=${manifest}`, collectionTask];
}

export function readInputs(path) {
  const inputs = JSON.parse(readFileSync(path, 'utf8'));
  if (![1, 2].includes(inputs.schemaVersion) || !Array.isArray(inputs.sources) || !Array.isArray(inputs.classpath)) throw new Error('Invalid Gradle input manifest');
  for (const [kind, paths] of [['sources', inputs.sources], ['classpath', inputs.classpath]]) {
    for (const item of paths) {
      if (typeof item !== 'string' || !isAbsolute(item) || /[\r\n]/.test(item)) throw new Error(`Expected absolute single-line ${kind} path`);
      if (!existsSync(item)) throw new Error(`Collected ${kind} path does not exist: ${item}`);
      const info = statSync(item);
      if (kind === 'sources' && (!info.isFile() || !/\.(kt|java)$/.test(item))) throw new Error(`Invalid source file: ${item}`);
      if (kind === 'classpath' && !info.isFile() && !info.isDirectory()) throw new Error(`Invalid classpath entry: ${item}`);
    }
  }
  if (!inputs.sources.some(path => path.endsWith('.kt'))) throw new Error('No Kotlin sources in selected compile task');
  if (!inputs.classpath.length) throw new Error('Selected compile task has no classpath');
  if (inputs.resourceInputs !== undefined) {
    const resources = inputs.resourceInputs;
    if (inputs.schemaVersion !== 2 || !resources || typeof resources.namespace !== 'string' ||
      !/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(resources.namespace) ||
      typeof resources.variant !== 'string' || !Array.isArray(resources.roots) || !resources.roots.length ||
      typeof resources.symbols !== 'string' || !isAbsolute(resources.symbols) || !statSync(resources.symbols).isFile()) {
      throw new Error('Invalid selected-variant resource inputs');
    }
    let priority = -1;
    for (const root of resources.roots) {
      if (!root || typeof root.sourceSet !== 'string' || !Number.isInteger(root.overlayPriority) || root.overlayPriority < 0 || root.overlayPriority < priority ||
        typeof root.path !== 'string' || !isAbsolute(root.path) || !statSync(root.path).isDirectory()) {
        throw new Error('Invalid ordered project resource root');
      }
      priority = root.overlayPriority;
    }
  }
  return inputs;
}

function runLogged(command, args, cwd, workDir, stage) {
  writeFileSync(join(workDir, `${stage}.command.json`), JSON.stringify({ command, args, cwd }, null, 2));
  const stdout = openSync(join(workDir, `${stage}.stdout.log`), 'wx');
  const stderr = openSync(join(workDir, `${stage}.stderr.log`), 'wx');
  try {
    const result = spawnSync(command, args, { cwd, stdio: ['ignore', stdout, stderr] });
    if (result.error) throw result.error;
    if (result.signal) throw new Error(`${stage} terminated by ${result.signal}`);
    return result.status;
  } finally { closeSync(stdout); closeSync(stderr); }
}

export function main(args) {
  if (args.includes('--help')) { process.stdout.write(help); return 0; }
  let workDir;
  let stage = 'configuration';
  try {
    const options = parseOptions(args);
    const dependencySources = options.dependencySourcesFile ?
      [...new Set(readFileSync(options.dependencySourcesFile, 'utf8').split(/\r?\n/).filter(path => path.length))] : [];
    for (const path of dependencySources) {
      if (!isAbsolute(path) || /[\r\n]/.test(path) || !/\.(kt|java)$/.test(path) || !existsSync(path) || !statSync(path).isFile())
        throw new Error(`Invalid dependency source path: ${path}`);
    }
    if (!existsSync(join(options.project, 'gradlew'))) throw new Error(`Gradle wrapper missing: ${join(options.project, 'gradlew')}`);
    if (options.output) {
      try { lstatSync(options.output); throw new Error(`Refusing to overwrite existing target: ${options.output}`); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    if (options.preflightOutput) {
      try { lstatSync(options.preflightOutput); throw new Error(`Refusing to overwrite existing preflight report: ${options.preflightOutput}`); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    workDir = options.workDir;
    if (workDir) { mkdirSync(dirname(workDir), { recursive: true }); mkdirSync(workDir); }
    else workDir = mkdtempSync(join(tmpdir(), 'kotlin-ets-project-'));
    const manifest = join(workDir, 'inputs.json');
    process.stderr.write(`Kotlin/ETS project evidence: ${workDir}\n`);
    stage = 'gradle';
    const status = runLogged('bash', gradleArguments(options, manifest), options.project, workDir, stage);
    if (status !== 0) throw new Error(`Gradle input collection failed (exit ${status}); see gradle.stdout.log and gradle.stderr.log`);
    const inputs = readInputs(manifest);
    const classpath = join(workDir, 'classpath.txt');
    const sources = join(workDir, 'sources.txt');
    writeFileSync(classpath, inputs.classpath.join('\n') + '\n', { flag: 'wx' });
    const combinedSources = [...new Set([...inputs.sources, ...dependencySources])];
    writeFileSync(sources, combinedSources.join('\n') + '\n', { flag: 'wx' });
    if (options.dependencySourcesFile) writeFileSync(join(workDir, 'dependency-sources.json'),
      JSON.stringify({ input: options.dependencySourcesFile, sources: dependencySources }, null, 2), { flag: 'wx' });
    if (options.collectOnly) {
      process.stdout.write(JSON.stringify({ ok: true, collectedOnly: true, inputs: manifest, sourceCount: combinedSources.length, classpathCount: inputs.classpath.length }) + '\n');
      return 0;
    }
    stage = 'compiler-environment';
    const environment = compilerEnvironment(inputs);
    const frontendArguments = join(workDir, 'frontend-arguments.txt');
    writeFileSync(frontendArguments, environment.arguments.join('\n') + '\n', { flag: 'wx' });
    writeFileSync(join(workDir, 'compiler-environment.json'), JSON.stringify(environment, null, 2), { flag: 'wx' });
    let imageResources = options.imageResources;
    if (!imageResources && inputs.resourceInputs) {
      stage = 'image-resources';
      const pack = materializeProjectImages({ resourceRoots: inputs.resourceInputs.roots,
        namespace: inputs.resourceInputs.namespace, variant: inputs.resourceInputs.variant,
        symbolsFile: inputs.resourceInputs.symbols, out: join(workDir, 'image-resources') });
      imageResources = pack.properties;
      writeFileSync(join(workDir, 'image-resources.json'), JSON.stringify(pack, null, 2), { flag: 'wx' });
    }
    let stringResources = options.stringResources;
    if (!stringResources && inputs.resourceInputs) {
      stage = 'string-resources';
      const pack = materializeProjectStrings({ resourceRoots: inputs.resourceInputs.roots,
        namespace: inputs.resourceInputs.namespace, variant: inputs.resourceInputs.variant,
        symbolsFile: inputs.resourceInputs.symbols, out: join(workDir, 'string-resources') });
      stringResources = pack.output;
      writeFileSync(join(workDir, 'string-resources.json'), JSON.stringify(pack, null, 2), { flag: 'wx' });
    }
    let fontResources = options.fontResources;
    if (!fontResources && inputs.resourceInputs) {
      stage = 'font-resources';
      const pack = materializeProjectFonts({ resourceRoots: inputs.resourceInputs.roots,
        namespace: inputs.resourceInputs.namespace, variant: inputs.resourceInputs.variant,
        symbolsFile: inputs.resourceInputs.symbols, out: join(workDir, 'font-resources') });
      fontResources = pack.properties;
      writeFileSync(join(workDir, 'font-resources.json'), JSON.stringify(pack, null, 2), { flag: 'wx' });
    }
    stage = 'compiler';
    const compilerArgs = [join(root, 'kotlin-ets'), '--mode', options.mode, options.outputFlag, options.output,
      '--unsupported-policy', options.unsupportedPolicy,
      '--project-compiler-version', environment.projectCompilerVersion,
      '--classpath-file', classpath, '--sources-file', sources, '--frontend-arguments-file', frontendArguments,
      ...(options.entry ? ['--entry', options.entry] : []),
      ...(imageResources ? ['--image-resources', imageResources] : []),
      ...(stringResources ? ['--string-resources', stringResources] : []),
      ...(fontResources ? ['--font-resources', fontResources] : [])];
    if (options.preflightOutput) compilerArgs.push('--preflight-out', options.preflightOutput);
    const result = runLogged('bash', compilerArgs, options.project, workDir, stage);
    process.stdout.write(readFileSync(join(workDir, 'compiler.stdout.log')));
    if (result !== 0) process.stderr.write(`Kotlin/ETS backend failed (exit ${result}); see ${join(workDir, 'compiler.stderr.log')}\n`);
    return result;
  } catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, code: 'PROJECT_INPUTS_FAILED', stage, message: error.message, workDir }) + '\n');
    return 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = main(process.argv.slice(2));
