#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, rmdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

function validateInputs({ resourceRoots, namespace, out, symbolsFile }) {
  if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(namespace ?? '')) {
    throw new Error('namespace must be an ASCII Java package name');
  }
  if (!Array.isArray(resourceRoots) || !resourceRoots.length) throw new Error('Project font resources require ordered resource roots');
  if (!isAbsolute(out ?? '') || !isAbsolute(symbolsFile ?? '')) throw new Error('Project font output and symbols must be absolute paths');
  const destination = resolve(out);
  if (existsSync(destination)) throw new Error(`Output already exists: ${destination}`);
  const seen = new Set();
  const roots = resourceRoots.map((root, index) => {
    if (!root || typeof root.sourceSet !== 'string' || !root.sourceSet || !Number.isInteger(root.overlayPriority) ||
      root.overlayPriority < 0 || !isAbsolute(root.path ?? '')) throw new Error(`Invalid project resource root at index ${index}`);
    const path = resolve(root.path);
    const stat = lstatSync(path);
    if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error(`Project resource root must be a real directory: ${path}`);
    if (seen.has(path)) throw new Error(`Duplicate project resource root: ${path}`);
    seen.add(path);
    const nested = relative(path, destination);
    if (nested === '' || (!nested.startsWith(`..${sep}`) && nested !== '..' && !isAbsolute(nested))) {
      throw new Error(`Project font output must not be inside resource root: ${path}`);
    }
    return { sourceSet: root.sourceSet, overlayPriority: root.overlayPriority, path };
  });
  for (let i = 1; i < roots.length; i++) if (roots[i].overlayPriority < roots[i - 1].overlayPriority) {
    throw new Error('Project resource roots must be ordered from lower to higher overlay priority');
  }
  return { destination, roots };
}

/** Materialize local TTF/OTF resources from the selected Android variant's module overlay. */
export function materializeProjectFonts({ resourceRoots, namespace, out, symbolsFile, variant }) {
  const { destination, roots } = validateInputs({ resourceRoots, namespace, out, symbolsFile });
  const symbols = new Set();
  for (const line of readFileSync(symbolsFile, 'utf8').split(/\r?\n/)) {
    const match = /^int\s+font\s+([a-z_][a-z0-9_]*)\s+(?:0x[0-9a-fA-F]+|\d+)\s*$/.exec(line);
    if (match) symbols.add(`${namespace}.R.font.${match[1]}`);
  }

  const selected = new Map();
  const unavailable = new Map();
  const qualified = new Map();
  for (const root of roots) for (const directory of readdirSync(root.path).sort()) {
    if (directory !== 'font' && !directory.startsWith('font-')) continue;
    const folder = join(root.path, directory);
    const folderStat = lstatSync(folder);
    if (folderStat.isSymbolicLink() || !folderStat.isDirectory()) throw new Error(`Font resource directory must be real: ${folder}`);
    for (const name of readdirSync(folder).sort()) {
      const path = join(folder, name);
      const stat = lstatSync(path);
      if (stat.isSymbolicLink() || !stat.isFile()) throw new Error(`Font resource must be a regular file: ${path}`);
      const extension = extname(name).toLowerCase();
      const resource = basename(name, extension);
      if (!/^[a-z_][a-z0-9_]*$/.test(resource)) continue;
      const symbol = `${namespace}.R.font.${resource}`;
      const source = { path, sourceSet: root.sourceSet, overlayPriority: root.overlayPriority };
      if (directory !== 'font') {
        const values = qualified.get(symbol) ?? [];
        values.push(source); qualified.set(symbol, values);
        continue;
      }
      const candidate = { symbol, path, extension, source, shadowed: [],
        reason: ['.ttf', '.otf'].includes(extension) ? null : `Unsupported Android font format ${extension || '(none)'} at ${path}` };
      const previous = selected.get(symbol) ?? unavailable.get(symbol);
      if (previous && previous.source.overlayPriority === root.overlayPriority) {
        throw new Error(`Ambiguous project font resource ${symbol} at overlay priority ${root.overlayPriority}: ${previous.path} and ${path}`);
      }
      if (previous && previous.source.overlayPriority > root.overlayPriority) continue;
      if (previous) candidate.shadowed = [previous.source, ...(previous.shadowed ?? [])];
      selected.delete(symbol); unavailable.delete(symbol);
      (candidate.reason ? unavailable : selected).set(symbol, candidate);
    }
  }
  for (const [symbol, sources] of qualified) if (!selected.has(symbol) && !unavailable.has(symbol)) {
    const source = sources.at(-1);
    unavailable.set(symbol, { symbol, path: source.path, source, shadowed: sources.slice(0, -1),
      reason: `Only qualified Android font variants exist for ${symbol}; target configuration selection is unavailable` });
  }
  for (const symbol of symbols) if (!selected.has(symbol) && !unavailable.has(symbol)) {
    unavailable.set(symbol, { symbol, path: null, source: null, shadowed: [],
      reason: `No ${symbol} file exists in collected module resource roots` });
  }
  for (const symbol of selected.keys()) if (!symbols.has(symbol)) {
    throw new Error(`Selected variant R.txt has no font symbol: ${symbol}`);
  }

  const materialized = [...selected.values()].sort((a, b) => a.symbol.localeCompare(b.symbol)).map(entry => ({
    ...entry,
    target: `${createHash('sha256').update(entry.symbol).digest('hex')}${entry.extension}`,
  }));
  mkdirSync(dirname(destination), { recursive: true });
  const stage = mkdtempSync(join(dirname(destination), `.${basename(destination)}-stage-`));
  let claimed = false;
  const published = [];
  try {
    mkdirSync(join(stage, 'fonts'));
    for (const entry of materialized) writeFileSync(join(stage, 'fonts', entry.target), readFileSync(entry.path), { flag: 'wx' });
    writeFileSync(join(stage, 'fonts.properties'), materialized.map(entry => `${entry.symbol}=fonts/${entry.target}\n`).join(''),
      { encoding: 'ascii', flag: 'wx' });
    const provenance = {
      schemaVersion: 1, namespace, variant, roots,
      resources: [
        ...materialized.map(entry => ({ symbol: entry.symbol, status: 'materialized', output: `fonts/${entry.target}`,
          source: entry.source, shadowed: entry.shadowed })),
        ...[...unavailable].map(([symbol, entry]) => ({ symbol, status: 'unsupported', reason: entry.reason,
          source: entry.source, shadowed: entry.shadowed ?? [] })),
      ].sort((a, b) => a.symbol.localeCompare(b.symbol)),
    };
    writeFileSync(join(stage, 'font-resource-origins.json'), JSON.stringify(provenance, null, 2) + '\n', { flag: 'wx' });
    mkdirSync(destination); claimed = true;
    for (const name of readdirSync(stage)) {
      renameSync(join(stage, name), join(destination, name));
      published.push(name);
    }
    return { output: destination, properties: join(destination, 'fonts.properties'),
      provenance: join(destination, 'font-resource-origins.json'), count: materialized.length, unsupportedCount: unavailable.size };
  } catch (error) {
    if (claimed) {
      for (const name of published) rmSync(join(destination, name), { recursive: true, force: true });
      try { rmdirSync(destination); } catch { /* Keep concurrent files. */ }
    }
    throw error;
  } finally { rmSync(stage, { recursive: true, force: true }); }
}

function main(args) {
  const values = {};
  for (let i = 0; i < args.length; i += 2) {
    if (!['--res-dir', '--namespace', '--out', '--symbols', '--variant'].includes(args[i]) || values[args[i]] !== undefined || !args[i + 1]) {
      throw new Error('Usage: node font-resources.mjs --res-dir /android/res --namespace example --out /fresh/output --symbols /R.txt');
    }
    values[args[i]] = args[i + 1];
  }
  const root = resolve(values['--res-dir']);
  return materializeProjectFonts({ namespace: values['--namespace'], out: resolve(values['--out']), symbolsFile: resolve(values['--symbols']),
    variant: values['--variant'] ?? 'manual', resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: root }] });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.stdout.write(`${JSON.stringify(main(process.argv.slice(2)))}\n`); }
  catch (error) { process.stderr.write(`Font resources: ${error.message}\n`); process.exitCode = 1; }
}
