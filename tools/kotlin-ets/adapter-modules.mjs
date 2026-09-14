import { mkdirSync, readFileSync, readdirSync, realpathSync, statSync, existsSync, writeFileSync } from 'node:fs';
import { delimiter, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const servicePath = 'META-INF/services/dev.ets.AdapterModule';
const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const identifier = '[\\p{L}\\p{Nl}\\p{Sc}\\p{Pc}][\\p{L}\\p{Nl}\\p{Sc}\\p{Pc}\\p{Mn}\\p{Mc}\\p{Nd}\\p{Cf}]*';
const providerName = new RegExp(`^${identifier}(?:\\.${identifier})*$`, 'u');

export function parseProviders(text, descriptor) {
  const providers = new Set();
  for (const [index, line] of text.split(/\r\n|\n|\r/).entries()) {
    const name = line.split('#', 1)[0].trim();
    if (!name) continue;
    if (!providerName.test(name)) throw new Error(`Invalid SPI provider at ${descriptor}:${index + 1}: ${name}`);
    providers.add(name);
  }
  if (providers.size === 0) throw new Error(`No SPI providers in ${descriptor}`);
  return [...providers].sort(compare);
}

function kotlinSources(directory, ancestors = new Set()) {
  const canonical = realpathSync(directory);
  if (ancestors.has(canonical)) throw new Error(`Cyclic adapter source directory: ${directory}`);
  const next = new Set(ancestors).add(canonical);
  return readdirSync(directory).sort(compare).flatMap(name => {
    if (name.startsWith('.')) return [];
    const path = join(directory, name), stat = statSync(path);
    if (stat.isDirectory()) return kotlinSources(path, next);
    return stat.isFile() && name.endsWith('.kt') ? [realpathSync(path)] : [];
  });
}

/** Module boundaries come from directories and SPI descriptors, never Kotlin text. */
export function discoverAdapterModules(root, external = process.env.KOTLIN_ETS_ADAPTER_DIRS ?? '') {
  const roots = [];
  const builtIn = join(resolve(root), 'adapters');
  if (existsSync(builtIn)) roots.push(builtIn);
  if (external !== '') {
    const requested = external.split(delimiter);
    if (requested.some(path => path === '')) throw new Error('KOTLIN_ETS_ADAPTER_DIRS contains an empty root');
    roots.push(...requested.map(path => resolve(path)));
  }
  const directories = new Set();
  for (const path of roots) {
    if (!existsSync(path) || !statSync(path).isDirectory()) throw new Error(`Adapter root is not a directory: ${path}`);
    if (existsSync(join(path, servicePath))) directories.add(realpathSync(path));
    else {
      for (const name of readdirSync(path).sort(compare)) {
        if (name.startsWith('.')) continue;
        const child = join(path, name);
        if (statSync(child).isDirectory()) directories.add(realpathSync(child));
        else if (name.endsWith('.kt')) throw new Error(`Adapter sources require a module SPI descriptor: ${child}`);
      }
    }
  }
  const modules = [...directories].sort(compare).map(directory => {
    const descriptor = join(directory, servicePath);
    if (!existsSync(descriptor) || !statSync(descriptor).isFile()) throw new Error(`Missing adapter SPI descriptor: ${descriptor}`);
    const sources = [...new Set(kotlinSources(directory))].sort(compare);
    if (sources.length === 0) throw new Error(`Adapter module has no Kotlin sources: ${directory}`);
    return { directory, descriptor, sources, providers: parseProviders(readFileSync(descriptor, 'utf8'), descriptor) };
  });
  return {
    modules,
    sources: [...new Set(modules.flatMap(module => module.sources))].sort(compare),
    providers: [...new Set(modules.flatMap(module => module.providers))].sort(compare),
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv.length !== 4) throw new Error('Usage: adapter-modules.mjs TOOL_ROOT BUILD_DIRECTORY');
    const discovered = discoverAdapterModules(process.argv[2]);
    const build = resolve(process.argv[3]);
    const descriptor = join(build, 'spi', servicePath);
    mkdirSync(dirname(descriptor), { recursive: true });
    writeFileSync(descriptor, discovered.providers.length ? discovered.providers.join('\n') + '\n' : '');
    writeFileSync(join(build, 'adapter-sources.list'), discovered.sources.map(path => path + '\0').join(''));
    writeFileSync(join(build, 'adapter-modules.json'), JSON.stringify(discovered, null, 2) + '\n');
  } catch (error) {
    console.error(`Adapter discovery failed: ${error.message}`);
    process.exitCode = 2;
  }
}
