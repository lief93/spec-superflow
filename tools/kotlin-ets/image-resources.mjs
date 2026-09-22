#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, rmdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const converterDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '../../skills/migrate-android-compose-to-harmony/scripts');
const vectorBridge = `
import base64, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from convert_android_vector import convert_vector
try:
    svg, metadata = convert_vector(Path(sys.argv[2]), {})
    if metadata['requires_target_tint'] or metadata['dynamic_color_tokens']:
        raise ValueError('vector requires target tint/theme metadata which image-resources.properties cannot represent')
    if metadata['requires_auto_mirroring']:
        raise ValueError('vector requires automatic mirroring which image-resources.properties cannot represent')
    print(json.dumps({'svg': base64.b64encode(svg).decode('ascii')}))
except Exception as error:
    print(str(error), file=sys.stderr)
    sys.exit(1)
`;

function exists(path) {
  try { lstatSync(path); return true; } catch (error) {
    if (error.code === 'ENOENT') return false;
    throw error;
  }
}

function convertVector(path) {
  const result = spawnSync('python3', ['-B', '-c', vectorBridge, converterDirectory, path], {
    encoding: 'utf8', timeout: 30000, maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error) throw new Error(`Vector conversion failed for ${path}: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`Vector conversion failed for ${path}: ${result.stderr.trim()}`);
  return Buffer.from(JSON.parse(result.stdout).svg, 'base64');
}

function bitmap(path, extension) {
  const bytes = readFileSync(path);
  const valid = extension === '.png'
    ? bytes.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex'))
    : extension === '.webp'
      ? bytes.length >= 20 && bytes.toString('ascii', 0, 4) === 'RIFF' && bytes.toString('ascii', 8, 12) === 'WEBP'
        && bytes.readUInt32LE(4) + 8 === bytes.length
      : bytes.length >= 4 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
        && bytes[bytes.length - 2] === 0xff && bytes[bytes.length - 1] === 0xd9;
  if (!valid) throw new Error(`Invalid ${extension.slice(1).toUpperCase()} file signature: ${path}`);
  return bytes;
}

export function materializeImages({ resDir, namespace, out, symbolsFile, include }) {
  if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(namespace ?? '')) {
    throw new Error('namespace must be an ASCII Java package name');
  }
  if (!isAbsolute(resDir ?? '') || !isAbsolute(out ?? '')) throw new Error('res-dir and out must be absolute paths');
  const source = resolve(resDir);
  const destination = resolve(out);
  const sourceStat = lstatSync(source);
  if (sourceStat.isSymbolicLink() || !sourceStat.isDirectory()) throw new Error(`res-dir must be a real directory, not a symlink: ${source}`);
  const nested = relative(source, destination);
  if (nested === '' || (!nested.startsWith(`..${sep}`) && nested !== '..' && !isAbsolute(nested))) {
    throw new Error('out must not be inside res-dir');
  }
  if (exists(destination)) throw new Error(`Output already exists: ${destination}`);
  const entries = [];
  const symbols = new Set();
  const selected = include === undefined ? null : new Set(include);
  if (selected && (!selected.size || [...selected].some(name => !/^[a-z_][a-z0-9_]*$/.test(name)))) {
    throw new Error('include requires nonempty drawable resource names');
  }
  for (const directory of readdirSync(source).sort()) {
    if (directory !== 'drawable' && !directory.startsWith('drawable-')) continue;
    const folder = join(source, directory);
    const folderStat = lstatSync(folder);
    if (folderStat.isSymbolicLink() || !folderStat.isDirectory()) throw new Error(`Drawable directory is not a real directory (symlink unsupported): ${folder}`);
    const names = readdirSync(folder).sort().filter(name => !selected || selected.has(basename(name, extname(name))));
    if (names.length && !['drawable', 'drawable-nodpi'].includes(directory)) {
      throw new Error(`Unsupported qualified drawable directory: ${folder}; no density/theme/API variant selection is available`);
    }
    for (const name of names) {
      const path = join(folder, name);
      const stat = lstatSync(path);
      if (stat.isSymbolicLink() || !stat.isFile()) throw new Error(`Drawable must be a regular file, not a symlink or directory: ${path}`);
      if (name.endsWith('.9.png')) throw new Error(`Unsupported 9-patch drawable: ${path}`);
      const extension = extname(name);
      if (!['.png', '.jpg', '.jpeg', '.webp', '.xml'].includes(extension)) throw new Error(`Unsupported drawable format ${extension}: ${path}`);
      if (extension === '.xml' && directory !== 'drawable') throw new Error(`XML vectors require unqualified drawable: ${path}`);
      const resource = basename(name, extension);
      if (!/^[a-z_][a-z0-9_]*$/.test(resource)) throw new Error(`Invalid Android drawable resource name: ${path}`);
      const symbol = `${namespace}.R.drawable.${resource}`;
      if (symbols.has(symbol)) throw new Error(`Ambiguous drawable symbol ${symbol}: multiple files or variants`);
      symbols.add(symbol);
      const target = `img_${createHash('sha256').update(symbol).digest('hex')}`;
      if (entries.some(entry => entry.target === target)) throw new Error(`Target resource name collision: ${symbol}`);
      entries.push({ path, extension, symbol, target });
    }
  }
  if (selected) for (const name of selected) {
    if (!symbols.has(`${namespace}.R.drawable.${name}`)) throw new Error(`Selected drawable is missing: ${name}`);
  }
  if (!entries.length) throw new Error(`No supported drawable resources found: ${source}`);
  let sourceIds;
  if (symbolsFile !== undefined) {
    if (!isAbsolute(symbolsFile)) throw new Error('symbols must be an absolute R.txt path');
    const ids = new Map(), numbers = new Set();
    for (const line of readFileSync(symbolsFile, 'utf8').split(/\r?\n/)) {
      const match = /^int\s+drawable\s+([a-z_][a-z0-9_]*)\s+(0x[0-9a-fA-F]+|\d+)\s*$/.exec(line);
      if (!match) continue;
      const symbol = `${namespace}.R.drawable.${match[1]}`;
      if (!symbols.has(symbol)) continue;
      const id = Number(match[2]);
      if (!Number.isInteger(id) || id <= 0 || id > 0x7fffffff || ids.has(symbol) || numbers.has(id)) {
        throw new Error(`Invalid or ambiguous R.txt image ID: ${symbol}`);
      }
      ids.set(symbol, id); numbers.add(id);
    }
    sourceIds = entries.map(entry => {
      if (!ids.has(entry.symbol)) throw new Error(`R.txt has no final image ID: ${entry.symbol}`);
      return `${entry.symbol} = ${ids.get(entry.symbol)}\n`;
    }).join('');
  }
  mkdirSync(dirname(destination), { recursive: true });
  const stage = mkdtempSync(join(dirname(destination), `.${basename(destination)}-stage-`));
  let claimed = false;
  let mediaPublished = false;
  let idsPublished = false;
  try {
    mkdirSync(join(stage, 'media'));
    for (const entry of entries) {
      const extension = entry.extension === '.xml' ? '.svg' : entry.extension === '.jpeg' ? '.jpg' : entry.extension;
      const bytes = entry.extension === '.xml' ? convertVector(entry.path) : bitmap(entry.path, entry.extension);
      writeFileSync(join(stage, 'media', `${entry.target}${extension}`), bytes, { flag: 'wx' });
    }
    const properties = entries.map(entry => `${entry.symbol} = ${entry.target}\n`).join('');
    writeFileSync(join(stage, 'image-resources.properties'), properties, { encoding: 'ascii', flag: 'wx' });
    if (sourceIds !== undefined) writeFileSync(join(stage, 'source-resource-ids.properties'), sourceIds, { encoding: 'ascii', flag: 'wx' });
    // Exclusive mkdir prevents overwriting even an empty existing directory.
    // The complete mapping is the last publication step, never a partial map.
    mkdirSync(destination);
    claimed = true;
    renameSync(join(stage, 'media'), join(destination, 'media'));
    mediaPublished = true;
    if (sourceIds !== undefined) {
      renameSync(join(stage, 'source-resource-ids.properties'), join(destination, 'source-resource-ids.properties'));
      idsPublished = true;
    }
    renameSync(join(stage, 'image-resources.properties'), join(destination, 'image-resources.properties'));
    return { output: destination, properties: join(destination, 'image-resources.properties'), count: entries.length };
  } catch (error) {
    if (idsPublished) rmSync(join(destination, 'source-resource-ids.properties'), { force: true });
    if (mediaPublished) rmSync(join(destination, 'media'), { recursive: true, force: true });
    if (claimed) {
      try { rmdirSync(destination); } catch { /* Keep unexpected concurrent files, never delete them. */ }
    }
    throw error;
  } finally {
    rmSync(stage, { recursive: true, force: true });
  }
}

function projectImageBytes(entry) {
  if (entry.extension === '.xml') return { bytes: convertVector(entry.path), extension: '.svg' };
  if (entry.extension === '.svg') {
    const bytes = readFileSync(entry.path);
    if (!/^\s*(?:<\?xml[^>]*>\s*)?<svg[\s>]/.test(bytes.toString('utf8'))) {
      throw new Error(`Invalid SVG document: ${entry.path}`);
    }
    return { bytes, extension: '.svg' };
  }
  return { bytes: bitmap(entry.path, entry.extension),
    extension: entry.extension === '.jpeg' ? '.jpg' : entry.extension };
}

function xmlKind(path) {
  const text = readFileSync(path, 'utf8').replace(/<\?xml[\s\S]*?\?>|<!--[\s\S]*?-->/g, '').trimStart();
  return /^<([A-Za-z0-9_-]+)/.exec(text)?.[1] ?? 'malformed';
}

/** Materialize the selected Android variant's module-owned image overlay. */
export function materializeProjectImages({ resourceRoots, namespace, out, symbolsFile, variant }) {
  if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(namespace ?? '')) {
    throw new Error('namespace must be an ASCII Java package name');
  }
  if (!Array.isArray(resourceRoots) || !resourceRoots.length) throw new Error('Project image resources require ordered resource roots');
  if (!isAbsolute(out ?? '') || !isAbsolute(symbolsFile ?? '')) throw new Error('Project image output and symbols must be absolute paths');
  const destination = resolve(out);
  if (exists(destination)) throw new Error(`Output already exists: ${destination}`);
  const rootPaths = new Set();
  const roots = resourceRoots.map((root, index) => {
    if (!root || typeof root.sourceSet !== 'string' || !root.sourceSet || !Number.isInteger(root.overlayPriority) || root.overlayPriority < 0 ||
      !isAbsolute(root.path ?? '')) throw new Error(`Invalid project resource root at index ${index}`);
    const path = resolve(root.path);
    const stat = lstatSync(path);
    if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error(`Project resource root must be a real directory: ${path}`);
    if (rootPaths.has(path)) throw new Error(`Duplicate project resource root: ${path}`);
    rootPaths.add(path);
    const nested = relative(path, destination);
    if (nested === '' || (!nested.startsWith(`..${sep}`) && nested !== '..' && !isAbsolute(nested))) {
      throw new Error(`Project image output must not be inside resource root: ${path}`);
    }
    return { sourceSet: root.sourceSet, overlayPriority: root.overlayPriority, path };
  });
  for (let i = 1; i < roots.length; i++) if (roots[i].overlayPriority < roots[i - 1].overlayPriority) {
    throw new Error('Project resource roots must be ordered from lower to higher overlay priority');
  }

  const ids = new Map();
  const idNumbers = new Set();
  for (const line of readFileSync(symbolsFile, 'utf8').split(/\r?\n/)) {
    const match = /^int\s+(drawable|mipmap)\s+([a-z_][a-z0-9_]*)\s+(0x[0-9a-fA-F]+|\d+)\s*$/.exec(line);
    if (!match) continue;
    const symbol = `${namespace}.R.${match[1]}.${match[2]}`;
    const id = Number(match[3]);
    if (!Number.isInteger(id) || id <= 0 || id > 0x7fffffff || ids.has(symbol) || idNumbers.has(id)) {
      throw new Error(`Invalid or duplicate selected-variant image ID: ${symbol}`);
    }
    ids.set(symbol, id); idNumbers.add(id);
  }

  const selected = new Map();
  const unavailable = new Map();
  const alternatives = new Map();
  const origin = (root, path) => ({ path, sourceSet: root.sourceSet, overlayPriority: root.overlayPriority });
  for (const root of roots) for (const directory of readdirSync(root.path).sort()) {
    const match = /^(drawable|mipmap)(.*)$/.exec(directory);
    if (!match) continue;
    const folder = join(root.path, directory);
    const folderStat = lstatSync(folder);
    if (folderStat.isSymbolicLink() || !folderStat.isDirectory()) throw new Error(`Image resource directory must be real: ${folder}`);
    for (const name of readdirSync(folder).sort()) {
      const path = join(folder, name);
      const stat = lstatSync(path);
      if (stat.isSymbolicLink() || !stat.isFile()) throw new Error(`Image resource must be a regular file: ${path}`);
      const extension = extname(name);
      const resource = basename(name, extension);
      if (!/^[a-z_][a-z0-9_]*$/.test(resource) || name.endsWith('.9.png')) continue;
      const symbol = `${namespace}.R.${match[1]}.${resource}`;
      const source = origin(root, path);
      const qualified = match[2] && match[2] !== '-nodpi';
      if (qualified) {
        const values = alternatives.get(symbol) ?? [];
        values.push(source); alternatives.set(symbol, values);
        continue;
      }
      const supported = ['.png', '.jpg', '.jpeg', '.webp', '.svg', '.xml'].includes(extension);
      const candidate = { path, extension, symbol, source, shadowed: [],
        reason: supported ? null : `Unsupported Android image format ${extension || '(none)'} at ${path}` };
      const previous = selected.get(symbol) ?? unavailable.get(symbol);
      if (previous && previous.source.overlayPriority === root.overlayPriority) {
        throw new Error(`Ambiguous project image resource ${symbol} at overlay priority ${root.overlayPriority}: ` +
          `${previous.path} and ${path}`);
      }
      if (previous && previous.source.overlayPriority > root.overlayPriority) continue;
      if (previous) candidate.shadowed = [previous.source, ...(previous.shadowed ?? [])];
      selected.delete(symbol); unavailable.delete(symbol);
      (candidate.reason ? unavailable : selected).set(symbol, candidate);
    }
  }
  for (const [symbol, sources] of alternatives) if (!selected.has(symbol) && !unavailable.has(symbol)) {
    const source = sources.at(-1);
    unavailable.set(symbol, { path: source.path, source, shadowed: sources.slice(0, -1),
      reason: `Only qualified Android image variants exist for ${symbol}; target density/theme selection is unavailable` });
  }

  const rendered = [];
  for (const entry of [...selected.values()].sort((a, b) => a.symbol.localeCompare(b.symbol))) {
    if (!ids.has(entry.symbol)) throw new Error(`Selected variant R.txt has no image symbol: ${entry.symbol}`);
    try {
      const renderedImage = projectImageBytes(entry);
      rendered.push({ ...entry, ...renderedImage,
        target: `img_${createHash('sha256').update(entry.symbol).digest('hex')}` });
    } catch (error) {
      selected.delete(entry.symbol);
      const kind = entry.extension === '.xml' ? xmlKind(entry.path) : null;
      unavailable.set(entry.symbol, { ...entry,
        reason: kind && kind !== 'vector' ? `Unsupported Android image XML <${kind}> at ${entry.path}` : error.message });
    }
  }
  for (const symbol of ids.keys()) if (!selected.has(symbol) && !unavailable.has(symbol)) {
    unavailable.set(symbol, { path: null, source: null, shadowed: [],
      reason: `No ${symbol} file exists in collected module resource roots` });
  }

  mkdirSync(dirname(destination), { recursive: true });
  const stage = mkdtempSync(join(dirname(destination), `.${basename(destination)}-stage-`));
  let claimed = false;
  const published = [];
  try {
    mkdirSync(join(stage, 'media'));
    for (const entry of rendered) writeFileSync(join(stage, 'media', `${entry.target}${entry.extension}`), entry.bytes, { flag: 'wx' });
    writeFileSync(join(stage, 'image-resources.properties'), rendered.map(entry => `${entry.symbol} = ${entry.target}\n`).join(''),
      { encoding: 'ascii', flag: 'wx' });
    writeFileSync(join(stage, 'source-resource-ids.properties'), rendered.map(entry => `${entry.symbol} = ${ids.get(entry.symbol)}\n`).join(''),
      { encoding: 'ascii', flag: 'wx' });
    writeFileSync(join(stage, 'unsupported-image-resources.properties'), [...unavailable].sort(([a], [b]) => a.localeCompare(b))
      .map(([symbol, entry]) => `${symbol} = ${Buffer.from(entry.reason).toString('base64')}\n`).join(''), { encoding: 'ascii', flag: 'wx' });
    writeFileSync(join(stage, 'unsupported-image-resource-ids.properties'), [...unavailable].filter(([symbol]) => ids.has(symbol))
      .sort(([a], [b]) => a.localeCompare(b)).map(([symbol, entry]) =>
        `${ids.get(symbol)} = ${Buffer.from(`Unsupported Android image resource ${symbol}: ${entry.reason}`).toString('base64')}\n`).join(''),
    { encoding: 'ascii', flag: 'wx' });
    const provenance = {
      schemaVersion: 1, namespace, variant, roots,
      resources: [
        ...rendered.map(entry => ({ symbol: entry.symbol, status: 'materialized', target: entry.target,
          output: `media/${entry.target}${entry.extension}`, source: entry.source, shadowed: entry.shadowed })),
        ...[...unavailable].map(([symbol, entry]) => ({ symbol, status: 'unsupported', reason: entry.reason,
          source: entry.source, shadowed: entry.shadowed ?? [] })),
      ].sort((a, b) => a.symbol.localeCompare(b.symbol)),
    };
    writeFileSync(join(stage, 'image-resource-origins.json'), JSON.stringify(provenance, null, 2) + '\n', { flag: 'wx' });
    mkdirSync(destination); claimed = true;
    for (const name of ['media', 'image-resources.properties', 'source-resource-ids.properties',
      'unsupported-image-resources.properties', 'unsupported-image-resource-ids.properties', 'image-resource-origins.json']) {
      renameSync(join(stage, name), join(destination, name));
      published.push(name);
    }
    return { output: destination, properties: join(destination, 'image-resources.properties'),
      provenance: join(destination, 'image-resource-origins.json'), count: rendered.length, unsupportedCount: unavailable.size };
  } catch (error) {
    if (claimed) {
      for (const name of published) rmSync(join(destination, name), { recursive: true, force: true });
      try { rmdirSync(destination); } catch { /* Keep unexpected concurrent files, never delete them. */ }
    }
    throw error;
  } finally {
    rmSync(stage, { recursive: true, force: true });
  }
}

function main(args) {
  const values = {};
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i];
    if (!['--res-dir', '--namespace', '--out', '--symbols', '--include'].includes(key) || values[key] !== undefined || !args[i + 1]) {
      throw new Error('Usage: node image-resources.mjs --res-dir /android/res --namespace example --out /fresh/output');
    }
    values[key] = args[i + 1];
  }
  return materializeImages({ resDir: values['--res-dir'], namespace: values['--namespace'], out: values['--out'],
    symbolsFile: values['--symbols'], include: values['--include']?.split(',') });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.stdout.write(`${JSON.stringify(main(process.argv.slice(2)))}\n`); }
  catch (error) { process.stderr.write(`Image resources: ${error.message}\n`); process.exitCode = 1; }
}
