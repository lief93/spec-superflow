import { spawnSync } from 'node:child_process';
import { closeSync, existsSync, lstatSync, mkdirSync, mkdtempSync, openSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compilerEnvironment } from './compiler-environment.mjs';

const root = dirname(fileURLToPath(import.meta.url));
const help = `Kotlin to ETS: Gradle project input
bash tools/kotlin-ets/kotlin-ets --project /path/to/android --module :app \\
  --variant debug --entry sample.Page --out /path/to/new/Page.ets

--compile-task compileKotlin   Use an exact local task instead of --variant
--mode language               Translate ordinary Kotlin instead of a page
--out-dir /path/to/new/modules Output separate ETS source modules instead of --out
--collect-only                Collect inputs without running the ETS backend
--work-dir /path/to/new/run    Fresh directory for input lists and command logs
--offline                     Ask Gradle to use cached dependencies only
--image-resources /path/image-resources.properties  Use materialized image resources

Uses the project's Gradle wrapper and compile prerequisites. It does not edit
build scripts, compile the selected Kotlin task, install an app or upload files.
Node.js 18+ and the backend's cached compiler dependencies are required.
`;

export function parseOptions(args) {
  const values = new Map();
  const flags = new Set(['--offline', '--collect-only']);
  const options = new Set(['--project', '--module', '--variant', '--compile-task', '--mode', '--entry', '--out', '--out-dir', '--work-dir', '--image-resources']);
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
  if (get('out') && get('out-dir')) throw new Error('Specify only one of --out or --out-dir');
  if (!get('collect-only')) {
    if (!get('out') && !get('out-dir')) throw new Error('--out or --out-dir is required');
    if (mode === 'page' && !get('entry')) throw new Error('--entry is required for page mode');
  }
  return { project: resolve(get('project')), module: get('module'), compileTask, mode,
    entry: get('entry'), output: get('out') || get('out-dir') ? resolve(get('out') || get('out-dir')) : undefined,
    outputFlag: get('out-dir') ? '--out-dir' : '--out', workDir: get('work-dir') ? resolve(get('work-dir')) : undefined,
    imageResources: get('image-resources') ? resolve(get('image-resources')) : undefined,
    offline: !!get('offline'), collectOnly: !!get('collect-only') };
}

export function gradleArguments(options, manifest) {
  return [join(options.project, 'gradlew'), '--no-daemon', '--no-configuration-cache', '--console=plain',
    ...(options.offline ? ['--offline'] : []), '-I', join(root, 'project-inputs.gradle'),
    `-PkotlinEtsModule=${options.module}`, `-PkotlinEtsCompileTask=${options.compileTask}`,
    `-PkotlinEtsInputsOutput=${manifest}`, 'kotlinEtsCollectInputs'];
}

export function readInputs(path) {
  const inputs = JSON.parse(readFileSync(path, 'utf8'));
  if (inputs.schemaVersion !== 1 || !Array.isArray(inputs.sources) || !Array.isArray(inputs.classpath)) throw new Error('Invalid Gradle input manifest');
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
    if (!existsSync(join(options.project, 'gradlew'))) throw new Error(`Gradle wrapper missing: ${join(options.project, 'gradlew')}`);
    if (options.output) {
      try { lstatSync(options.output); throw new Error(`Refusing to overwrite existing target: ${options.output}`); }
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
    writeFileSync(sources, inputs.sources.join('\n') + '\n', { flag: 'wx' });
    if (options.collectOnly) {
      process.stdout.write(JSON.stringify({ ok: true, collectedOnly: true, inputs: manifest, sourceCount: inputs.sources.length, classpathCount: inputs.classpath.length }) + '\n');
      return 0;
    }
    stage = 'compiler-environment';
    const environment = compilerEnvironment(inputs);
    const frontendArguments = join(workDir, 'frontend-arguments.txt');
    writeFileSync(frontendArguments, environment.arguments.join('\n') + '\n', { flag: 'wx' });
    writeFileSync(join(workDir, 'compiler-environment.json'), JSON.stringify(environment, null, 2), { flag: 'wx' });
    stage = 'compiler';
    const compilerArgs = [join(root, 'kotlin-ets'), '--mode', options.mode, options.outputFlag, options.output,
      '--classpath-file', classpath, '--sources-file', sources, '--frontend-arguments-file', frontendArguments,
      ...(options.entry ? ['--entry', options.entry] : []),
      ...(options.imageResources ? ['--image-resources', options.imageResources] : [])];
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
