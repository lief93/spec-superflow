import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync,
} from 'node:fs';
import { delimiter, dirname, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { discoverAdapterModules } from './adapter-modules.mjs';

const root = dirname(fileURLToPath(import.meta.url));
const categories = ['language_semantics', 'standard_library', 'neutral_compose_widget',
  'modifier', 'resources', 'project_dependencies'];
const help = `Kotlin/ETS offline project preflight
node tools/kotlin-ets/offline-preflight.mjs \\
  --project /absolute/path/to/project --module :app --variant debug \\
  --mode page --entry sample.Page --evidence /absolute/path/to/fresh-evidence

Required: --project, --module, exactly one of --variant/--compile-task,
--mode (page or language), and --evidence. Page mode also requires --entry.
Optional: --dependency-sources-file and repeatable --adapter-dir.

The command always asks Gradle to work offline. It writes local raw evidence under
raw/ and a path-redacted, review-before-transfer package under share/. Existing
evidence directories are never overwritten.
`;

const compare = (left, right) => left < right ? -1 : left > right ? 1 : 0;
const within = (parent, child) => child === parent || child.startsWith(parent.endsWith(sep) ? parent : parent + sep);
const readJson = path => {
  if (!existsSync(path)) return null;
  try { return JSON.parse(readFileSync(path, 'utf8')); }
  catch { return null; }
};
const sha256 = path => createHash('sha256').update(readFileSync(path)).digest('hex');

export function parseOfflineOptions(args) {
  const values = new Map();
  const adapterDirs = [];
  const options = new Set(['--project', '--module', '--variant', '--compile-task', '--mode', '--entry',
    '--evidence', '--dependency-sources-file', '--adapter-dir']);
  for (let index = 0; index < args.length; index++) {
    const key = args[index];
    if (!options.has(key)) throw new Error(`Unknown offline preflight option: ${key}`);
    const value = args[++index];
    if (!value || value.startsWith('--')) throw new Error(`Missing value for ${key}`);
    if (key === '--adapter-dir') adapterDirs.push(resolve(value));
    else {
      if (values.has(key)) throw new Error(`Duplicate option: ${key}`);
      values.set(key, value);
    }
  }
  const get = key => values.get(`--${key}`);
  for (const required of ['project', 'module', 'mode', 'evidence']) {
    if (!get(required)) throw new Error(`--${required} is required`);
  }
  if (Boolean(get('variant')) === Boolean(get('compile-task')))
    throw new Error('Specify exactly one of --variant or --compile-task');
  if (!/^:(?:[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)*)?$/.test(get('module')))
    throw new Error('Use an absolute Gradle module path, for example :app');
  if (!['page', 'language'].includes(get('mode'))) throw new Error('--mode must be page or language');
  if (get('mode') === 'page' && !get('entry')) throw new Error('--entry is required for page mode');
  if (get('entry') && !/^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+$/.test(get('entry')))
    throw new Error('--entry must be a fully-qualified declaration name');
  if (get('variant') && !/^[A-Za-z][A-Za-z0-9_]*$/.test(get('variant')))
    throw new Error('Invalid variant name');
  if (get('compile-task') && !/^[A-Za-z][A-Za-z0-9_]*$/.test(get('compile-task')))
    throw new Error('Use a local Kotlin compile task name without a module prefix');
  const project = resolve(get('project'));
  const evidence = resolve(get('evidence'));
  if (within(project, evidence)) throw new Error('--evidence must be outside the project tree');
  return { project, module: get('module'), variant: get('variant'), compileTask: get('compile-task'),
    mode: get('mode'), entry: get('entry'), evidence, adapterDirs,
    dependencySourcesFile: get('dependency-sources-file') ? resolve(get('dependency-sources-file')) : null };
}

export function createRedactor({ project, evidence, extraRoots = [] }) {
  const roots = [
    [evidence, '$EVIDENCE'], [project, '$PROJECT'], [root, '$TOOL'],
    [process.env.GRADLE_USER_HOME, '$GRADLE_HOME'], [process.env.ANDROID_HOME, '$ANDROID_SDK'],
    [process.env.ANDROID_SDK_ROOT, '$ANDROID_SDK'], [process.env.JAVA_HOME, '$JAVA_HOME'],
    [process.env.HOME, '$HOME'], ...extraRoots,
  ].filter(([path]) => path).map(([path, token]) => [resolve(path), token])
    .sort((left, right) => right[0].length - left[0].length);
  const text = value => {
    let redacted = value;
    for (const [path, token] of roots) redacted = redacted.replaceAll(path, token);
    return redacted;
  };
  const value = input => {
    if (typeof input === 'string') return text(input);
    if (Array.isArray(input)) return input.map(value);
    if (input && typeof input === 'object') return Object.fromEntries(
      Object.entries(input).map(([key, item]) => [key, value(item)]));
    return input;
  };
  return { text, value, tokens: Object.fromEntries(roots.map(([, token]) => [token, true])) };
}

function dependencyCategory(path, project) {
  const normalized = resolve(path);
  if (within(project, normalized)) return 'project_outputs';
  if (normalized.includes(`${sep}.gradle${sep}caches${sep}transforms${sep}`)) return 'android_transforms';
  if (normalized.includes(`${sep}.gradle${sep}caches${sep}modules-2${sep}`)) return 'external_modules';
  if (normalized.includes(`${sep}Android${sep}sdk${sep}`) || normalized.includes(`${sep}android-sdk${sep}`))
    return 'android_sdk';
  if (process.env.JAVA_HOME && within(resolve(process.env.JAVA_HOME), normalized)) return 'jdk';
  return 'other';
}

function sourceLocation(source) {
  return { file: source.file, line: source.line, column: source.column,
    endLine: source.endLine, endColumn: source.endColumn };
}

function location(call) {
  return sourceLocation(call.firstUnsupportedNode?.source ?? call.source);
}

function gap(call) {
  return { symbol: call.resolvedSymbol, kind: call.firstUnsupportedNode?.kind,
    message: call.firstUnsupportedNode?.message, responsibleModule: call.responsibleModule,
    source: location(call) };
}

function nodeGap(node) {
  return { symbol: node.symbol, kind: node.kind, message: node.message,
    responsibleModule: node.responsibleModule, source: sourceLocation(node.source) };
}

function combinedCoverage(report, names) {
  const values = names.map(name => report?.coverage?.[name]).filter(Boolean);
  const total = values.reduce((sum, value) => sum + value.total, 0);
  const recognized = values.reduce((sum, value) => sum + value.recognized, 0);
  return { total, recognized, unsupported: total - recognized,
    percentage: total === 0 ? null : Math.floor(recognized * 10000 / total) / 100 };
}

function pluginClassification(environment) {
  const loaded = [];
  const args = environment?.arguments ?? [];
  for (const argument of args) {
    if (argument.startsWith('-Xplugin=')) loaded.push(...argument.slice('-Xplugin='.length).split(','));
  }
  const excluded = (environment?.excluded ?? []).filter(value =>
    /plugin|compose|serialization|scripting/i.test(`${value.argument} ${value.reason}`));
  return { loaded: loaded.sort(compare), excluded };
}

export function buildOfflineSummary({ options, inputs, environment, report, diagnosis, adapters,
  projectResult, backendExit, backendError }) {
  const unsupported = report?.calls?.filter(call => call.firstUnsupportedNode) ?? [];
  const attached = unsupported.map(gap);
  const first = report?.firstUnsupportedNode;
  const firstAttached = first && unsupported.some(call => {
    const node = call.firstUnsupportedNode;
    return node?.kind === first.kind && node?.source?.file === first.source?.file &&
      node?.source?.start === first.source?.start && node?.source?.end === first.source?.end;
  });
  const detached = first && !firstAttached ? [nodeGap(first)] : [];
  const projectGaps = unsupported.filter(call => call.category === 'project_dependencies').map(gap)
    .concat(detached.filter(value => value.responsibleModule?.includes('/adapters/')));
  const languageGaps = unsupported.filter(call => call.category === 'language_semantics').map(gap)
    .concat(detached.filter(value => value.responsibleModule?.includes('/language/')));
  const defaults = (report?.calls ?? []).flatMap(call => call.argumentResolutions
    .filter(value => value.resolution === 'source_default')
    .map(value => ({ symbol: call.resolvedSymbol, parameter: value.parameter, resolution: value.resolution,
      source: sourceLocation(call.source) })));
  const dependencies = {};
  for (const path of inputs?.classpath ?? []) {
    const category = dependencyCategory(path, options.project);
    (dependencies[category] ??= []).push(path);
  }
  for (const values of Object.values(dependencies)) values.sort(compare);
  const preflightComplete = Boolean(report);
  const generated = Boolean(projectResult?.ok && projectResult.output && existsSync(projectResult.output));
  const status = preflightComplete ? (projectResult?.ok ? projectResult.status : 'blocked') : 'collection_failed';
  return {
    schemaVersion: 1, status, preflightComplete, targetGenerated: generated, backendExit,
    backendError: backendError ?? null,
    project: { root: options.project, module: options.module, variant: options.variant ?? null,
      compileTask: options.compileTask ?? null, mode: options.mode, entry: options.entry ?? null,
      offline: true, unsupportedPolicy: options.mode === 'page' ? 'report' : 'error' },
    inputs: inputs ? { task: inputs.task ?? null, sourceCount: inputs.sources.length,
      kotlinSourceCount: inputs.sources.filter(path => extname(path) === '.kt').length,
      javaSourceCount: inputs.sources.filter(path => extname(path) === '.java').length,
      classpathCount: inputs.classpath.length, omittedClasspath: inputs.omittedClasspath ?? [],
      resourceNamespace: inputs.resourceInputs?.namespace ?? null,
      resourceVariant: inputs.resourceInputs?.variant ?? null,
      resourceRootCount: inputs.resourceInputs?.roots?.length ?? 0 } : null,
    compiler: environment ? { projectCompilerVersion: environment.projectCompilerVersion,
      frontendCompilerVersion: environment.frontendCompilerVersion,
      compatibilityDecision: environment.compatibilityDecision,
      retainedArguments: environment.arguments, excludedArguments: environment.excluded } : null,
    dependencies: { total: inputs?.classpath?.length ?? 0,
      categories: Object.fromEntries(Object.entries(dependencies).sort(([left], [right]) => compare(left, right))
        .map(([name, paths]) => [name, { count: paths.length, entries: paths }])) },
    compilerPlugins: pluginClassification(environment),
    adapters: { providers: adapters?.providers ?? [], modules: (adapters?.modules ?? []).map(module => ({
      directory: module.directory, providers: module.providers, sourceCount: module.sources.length })) },
    coverage: report ? { categories: report.coverage,
      compose: combinedCoverage(report, ['neutral_compose_widget', 'modifier', 'resources']),
      businessAndDependencies: report.coverage.project_dependencies } : null,
    unsupportedLanguageNodes: languageGaps,
    projectAdapterGaps: projectGaps,
    unsupportedCalls: attached.concat(detached),
    explicitSourceDefaults: defaults,
    silentFallbackGate: { enforced: true, sourceDefaultsRecorded: defaults.length,
      degradationsRecorded: diagnosis?.degradationCount ?? diagnosis?.degradations?.length ?? 0,
      blockingFailureRecorded: Boolean(diagnosis?.blockingFailure) },
    diagnosis: diagnosis ?? null,
  };
}

function markdownTable(rows) {
  if (rows.length === 0) return '_None._\n';
  const headers = Object.keys(rows[0]);
  const cell = value => String(value ?? '').replaceAll('|', '\\|').replaceAll('\n', ' ');
  return `| ${headers.join(' | ')} |\n| ${headers.map(() => '---').join(' | ')} |\n` +
    rows.map(row => `| ${headers.map(header => cell(row[header])).join(' | ')} |`).join('\n') + '\n';
}

export function renderOfflineDiagnosis(summary) {
  const coverageRows = categories.map(category => ({ category,
    total: summary.coverage?.categories?.[category]?.total ?? 0,
    recognized: summary.coverage?.categories?.[category]?.recognized ?? 0,
    unsupported: summary.coverage?.categories?.[category]?.unsupported ?? 0,
    percentage: summary.coverage?.categories?.[category]?.percentage ?? 'n/a' }));
  const gaps = values => values.map(value => ({ kind: value.kind, symbol: value.symbol,
    location: `${value.source.file}:${value.source.line}:${value.source.column}`,
    message: value.message }));
  const defaults = summary.explicitSourceDefaults.map(value => ({ symbol: value.symbol,
    parameter: value.parameter, location: `${value.source.file}:${value.source.line}:${value.source.column}` }));
  const dependencyRows = Object.entries(summary.dependencies.categories).map(([category, value]) =>
    ({ category, count: value.count }));
  const pluginRows = [
    ...summary.compilerPlugins.loaded.map(path => ({ disposition: 'loaded', input: path, reason: '' })),
    ...summary.compilerPlugins.excluded.map(value => ({ disposition: 'excluded', input: value.argument,
      reason: value.reason })),
  ];
  const adapterRows = summary.adapters.modules.map(value => ({ providers: value.providers.join(', '),
    sourceCount: value.sourceCount, directory: value.directory }));
  const degradationRows = (summary.diagnosis?.degradations ?? []).map(value => ({ action: value.action,
    capability: value.capability, location: `${value.source?.file}:${value.source?.line}:${value.source?.column}`,
    impact: value.impact }));
  return `# Kotlin/ETS offline preflight diagnosis

- Status: **${summary.status}**
- Preflight complete: **${summary.preflightComplete}**
- Target generated: **${summary.targetGenerated}**
- Project: \`${summary.project.root}\`
- Module: \`${summary.project.module}\`
- Variant/task: \`${summary.project.variant ?? summary.project.compileTask}\`
- Mode/entry: \`${summary.project.mode}\` / \`${summary.project.entry ?? 'n/a'}\`
- Offline Gradle resolution: **enabled**

No unknown call or default value is silently accepted. Source defaults and approved degradations are listed below;
blocking failures leave no generated target.

## Compiler environment

| project compiler | frontend compiler | compatibility |
| --- | --- | --- |
| ${summary.compiler?.projectCompilerVersion ?? 'unavailable'} | ${summary.compiler?.frontendCompilerVersion ?? 'unavailable'} | ${summary.compiler?.compatibilityDecision ?? 'unavailable'} |

Sources: ${summary.inputs?.sourceCount ?? 0} total (${summary.inputs?.kotlinSourceCount ?? 0} Kotlin,
${summary.inputs?.javaSourceCount ?? 0} Java); classpath: ${summary.inputs?.classpathCount ?? 0};
resource roots: ${summary.inputs?.resourceRootCount ?? 0}.

## Dependency classification

${markdownTable(dependencyRows)}
## Compiler plugin classification

${markdownTable(pluginRows)}
## Adapter modules

${markdownTable(adapterRows)}
## API coverage

${markdownTable(coverageRows)}
Combined Compose/Modifier/resources coverage: ${summary.coverage?.compose?.recognized ?? 0}/${summary.coverage?.compose?.total ?? 0}.
Business/dependency API coverage: ${summary.coverage?.businessAndDependencies?.recognized ?? 0}/${summary.coverage?.businessAndDependencies?.total ?? 0}.

## Explicit source defaults

${markdownTable(defaults)}
## Unsupported language nodes

${markdownTable(gaps(summary.unsupportedLanguageNodes))}
## Project adapter and dependency gaps

${markdownTable(gaps(summary.projectAdapterGaps))}
## All unsupported calls

${markdownTable(gaps(summary.unsupportedCalls))}
## Approved degradations

${markdownTable(degradationRows)}
## Blocking failure

${summary.diagnosis?.blockingFailure ? `- ${summary.diagnosis.blockingFailure.code}: ${summary.diagnosis.blockingFailure.message}\n` : '_None._\n'}
## Collection or compiler setup failure

${summary.backendError ? `- ${summary.backendError}\n` : '_None._\n'}
## Transfer boundary

Only files in this \`share/\` directory belong in the return package. Raw source lists, classpaths, Gradle logs,
compiler logs, generated ETS, and the unredacted input manifest remain under \`raw/\` and are excluded.
Review project-relative filenames, symbols, and diagnostic messages before transfer because they describe project code.
`;
}

function filesBelow(directory, prefix = '') {
  if (!existsSync(directory)) return [];
  return readdirSync(directory, { withFileTypes: true }).sort((left, right) => compare(left.name, right.name))
    .flatMap(entry => {
      const path = join(directory, entry.name), name = join(prefix, entry.name);
      return entry.isDirectory() ? filesBelow(path, name) : [name];
    });
}

function resultFrom(stdout) {
  const lines = stdout.trim().split(/\r?\n/).filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index--) {
    try { return JSON.parse(lines[index]); } catch {}
  }
  return null;
}

function writeJson(path, value) {
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
}

export function main(args) {
  if (args.includes('--help')) { process.stdout.write(help); return 0; }
  let options;
  try { options = parseOfflineOptions(args); }
  catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, code: 'OFFLINE_PREFLIGHT_CONFIGURATION', message: error.message }) + '\n');
    return 1;
  }
  try {
    if (!existsSync(join(options.project, 'gradlew'))) throw new Error(`Gradle wrapper missing: ${join(options.project, 'gradlew')}`);
    if (existsSync(options.evidence)) throw new Error(`Refusing to overwrite existing evidence: ${options.evidence}`);
    for (const path of options.adapterDirs) if (!statSync(path).isDirectory()) throw new Error(`Adapter directory is not a directory: ${path}`);
    if (options.dependencySourcesFile && !statSync(options.dependencySourcesFile).isFile())
      throw new Error(`Dependency sources file is not a file: ${options.dependencySourcesFile}`);
    mkdirSync(options.evidence, { recursive: false });
    const raw = join(options.evidence, 'raw'), share = join(options.evidence, 'share');
    mkdirSync(raw); mkdirSync(share);
    const projectRun = join(raw, 'project-run');
    const output = join(raw, 'target.ets');
    const preflight = join(raw, 'core-profile.json');
    const projectArgs = [join(root, 'project.mjs'), '--project', options.project, '--module', options.module,
      ...(options.variant ? ['--variant', options.variant] : ['--compile-task', options.compileTask]),
      '--mode', options.mode, ...(options.entry ? ['--entry', options.entry] : []),
      '--out', output, '--preflight-out', preflight, '--work-dir', projectRun, '--offline',
      '--unsupported-policy', options.mode === 'page' ? 'report' : 'error',
      ...(options.dependencySourcesFile ? ['--dependency-sources-file', options.dependencySourcesFile] : [])];
    const external = options.adapterDirs.join(delimiter);
    const env = { ...process.env };
    if (external) env.KOTLIN_ETS_ADAPTER_DIRS = external;
    else delete env.KOTLIN_ETS_ADAPTER_DIRS;
    writeJson(join(raw, 'command.json'), { command: process.execPath, args: projectArgs,
      environment: { offline: true, adapterDirectories: options.adapterDirs } });
    let adapters = null, backendError = null;
    try { adapters = discoverAdapterModules(root, external); }
    catch (error) { backendError = `Adapter discovery failed: ${error.message}`; }
    let result = { status: 1, stdout: '', stderr: '', error: null };
    if (!backendError) result = spawnSync(process.execPath, projectArgs, { encoding: 'utf8', env,
      timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
    writeFileSync(join(raw, 'stdout.log'), result.stdout ?? '', { flag: 'wx' });
    writeFileSync(join(raw, 'stderr.log'), result.stderr ?? '', { flag: 'wx' });
    backendError ??= result.error?.message ?? (result.signal ? `Project preflight terminated by ${result.signal}` : null);
    const inputs = readJson(join(projectRun, 'inputs.json'));
    const environment = readJson(join(projectRun, 'compiler-environment.json'));
    const report = readJson(preflight);
    const projectResult = resultFrom(result.stdout ?? '');
    const diagnosis = readJson(output + '.diagnosis.json') ??
      (report && projectResult?.ok === false ? { schemaVersion: 1, status: 'blocked', equivalenceVerified: false,
        degradationCount: 0, degradations: [], blockingFailure: { code: projectResult.code,
          message: projectResult.message, source: projectResult.source ?? null } } : null);
    backendError ??= !report && projectResult?.ok === false ?
      `${projectResult.stage ?? projectResult.code ?? 'project'}: ${projectResult.message}` : null;
    const summary = buildOfflineSummary({ options, inputs, environment, report, diagnosis, adapters,
      projectResult, backendExit: result.status, backendError });
    const externalSources = [...new Set((inputs?.sources ?? []).filter(path => !within(options.project, path))
      .map(path => dirname(path)))].sort(compare).map((path, index) => [path, `$EXTERNAL_SOURCE_${index + 1}`]);
    const externalDependencies = [...new Set((inputs?.classpath ?? [])
      .filter(path => dependencyCategory(path, options.project) === 'other')
      .map(path => statSync(path).isDirectory() ? path : dirname(path)))].sort(compare)
      .map((path, index) => [path, `$EXTERNAL_DEPENDENCY_${index + 1}`]);
    const adapterRoots = options.adapterDirs.map((path, index) => [path, `$ADAPTER_${index + 1}`]);
    const redactor = createRedactor({ ...options,
      extraRoots: [...externalSources, ...externalDependencies, ...adapterRoots] });
    const safeSummary = redactor.value(summary);
    writeJson(join(share, 'summary.json'), safeSummary);
    if (report) writeJson(join(share, 'core-profile.json'), redactor.value(report));
    if (environment) writeJson(join(share, 'compiler-environment.json'), redactor.value(environment));
    if (adapters) writeJson(join(share, 'adapter-modules.json'), redactor.value({ schemaVersion: 1,
      modules: adapters.modules.map(module => ({ directory: module.directory,
        providers: module.providers, sourceCount: module.sources.length })) }));
    writeFileSync(join(share, 'diagnosis.md'), renderOfflineDiagnosis(safeSummary), { flag: 'wx' });
    const included = filesBelow(share).map(path => ({ path, sha256: sha256(join(share, path)),
      sensitivity: path === 'diagnosis.md' || path === 'core-profile.json' ?
        'Contains project-relative filenames, symbols and diagnostic messages; review before transfer' :
        'Infrastructure paths replaced with stable tokens' }));
    included.push({ path: 'evidence-manifest.json', sha256: null,
      sensitivity: 'Self-describing manifest; verify the completed archive separately' });
    const manifest = { schemaVersion: 1, readyToPackage: summary.preflightComplete,
      packageFrom: '$EVIDENCE/share',
      packageCommand: 'tar -czf kotlin-ets-offline-preflight.tar.gz -C "$EVIDENCE/share" .',
      included, localOnly: filesBelow(raw).map(path => ({ path: join('raw', path),
        reason: 'Unredacted local evidence; do not transfer without separate review' })),
      redaction: { infrastructurePaths: Object.keys(redactor.tokens),
        reviewRequired: 'Project-relative filenames, API symbols and diagnostic messages are intentionally retained for diagnosis' } };
    writeJson(join(share, 'evidence-manifest.json'), manifest);
    process.stdout.write(JSON.stringify({ ok: summary.preflightComplete, status: summary.status,
      evidence: options.evidence, share, diagnosis: join(share, 'diagnosis.md'),
      manifest: join(share, 'evidence-manifest.json') }) + '\n');
    return summary.preflightComplete ? 0 : 1;
  } catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, code: 'OFFLINE_PREFLIGHT_FAILED',
      message: error.message, evidence: options.evidence }) + '\n');
    return 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  process.exitCode = main(process.argv.slice(2));
