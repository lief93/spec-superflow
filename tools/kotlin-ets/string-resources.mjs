#!/usr/bin/env node
import { existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, rmdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const RESOURCE_TYPES = new Map([['string', 'string'], ['plurals', 'plurals'], ['string-array', 'array']]);
const QUANTITIES = new Set(['zero', 'one', 'two', 'few', 'many', 'other']);

function decodeEntities(value, path) {
  if (value.replace(/&[^;\s]+;/g, '').includes('&')) throw new Error(`Unescaped ampersand in ${path}`);
  return value.replace(/&([^;\s]+);/g, (_, entity) => {
    if (entity === 'amp') return '&';
    if (entity === 'lt') return '<';
    if (entity === 'gt') return '>';
    if (entity === 'quot') return '"';
    if (entity === 'apos') return "'";
    if (!/^#(?:x[0-9a-fA-F]+|\d+)$/.test(entity)) throw new Error(`Unsupported XML entity &${entity}; in ${path}`);
    const number = entity[1]?.toLowerCase() === 'x' ? Number.parseInt(entity.slice(2), 16) : Number(entity.slice(1));
    if (!Number.isInteger(number) || number < 0 || number > 0x10ffff) throw new Error(`Invalid XML entity in ${path}`);
    return String.fromCodePoint(number);
  });
}

function attributes(source, path) {
  const result = {};
  let rest = source.trim();
  while (rest) {
    const match = /^([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*("([^"]*)"|'([^']*)')\s*/s.exec(rest);
    if (!match || result[match[1]] !== undefined) throw new Error(`Invalid XML attributes in ${path}`);
    result[match[1]] = decodeEntities(match[3] ?? match[4], path);
    rest = rest.slice(match[0].length);
  }
  return result;
}

function parseXml(path) {
  const source = readFileSync(path, 'utf8').replace(/^\uFEFF/, '');
  if (/<!DOCTYPE|<!ENTITY/i.test(source)) throw new Error(`DTD and custom entities are unsupported: ${path}`);
  const root = { tag: null, attrs: {}, children: [], text: '' };
  const stack = [root];
  const tokens = source.match(/<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<!\[CDATA\[[\s\S]*?\]\]>|<[^>]+>|[^<]+/g) ?? [];
  for (const token of tokens) {
    if (token.startsWith('<!--') || token.startsWith('<?')) continue;
    if (token.startsWith('<![CDATA[')) {
      stack.at(-1).text += token.slice(9, -3);
      continue;
    }
    if (!token.startsWith('<')) {
      stack.at(-1).text += decodeEntities(token, path);
      continue;
    }
    const close = /^<\/\s*([A-Za-z_:][A-Za-z0-9_.:-]*)\s*>$/.exec(token);
    if (close) {
      if (stack.length === 1 || stack.at(-1).tag !== close[1]) throw new Error(`Mismatched XML element ${token} in ${path}`);
      stack.pop();
      continue;
    }
    const open = /^<\s*([A-Za-z_:][A-Za-z0-9_.:-]*)([\s\S]*?)(\/?)>$/.exec(token);
    if (!open) throw new Error(`Invalid XML element ${token} in ${path}`);
    const node = { tag: open[1], attrs: attributes(open[2], path), children: [], text: '' };
    stack.at(-1).children.push(node);
    if (!open[3]) stack.push(node);
  }
  if (stack.length !== 1 || root.children.length !== 1 || root.children[0].tag !== 'resources' || root.text.trim()) {
    throw new Error(`Expected one <resources> document: ${path}`);
  }
  return root.children[0];
}

function androidText(node, path) {
  if (node.children.length) throw new Error(`styled spans are unsupported: ${path}`);
  let value = node.text;
  const quoted = /^\s*"([\s\S]*)"\s*$/.exec(value);
  value = quoted ? quoted[1] : value.trim().replace(/\s+/g, ' ');
  let decoded = '';
  for (let i = 0; i < value.length; i++) {
    if (value[i] !== '\\') { decoded += value[i]; continue; }
    const escaped = value[++i];
    if (escaped === undefined) throw new Error(`trailing Android escape is unsupported: ${path}`);
    const replacements = { n: '\n', r: '\r', t: '\t', '\\': '\\', "'": "'", '"': '"', '@': '@', '?': '?' };
    if (replacements[escaped] === undefined) throw new Error(`Android escape \\${escaped} is unsupported: ${path}`);
    decoded += replacements[escaped];
  }
  if (/^\s*[@?]/.test(decoded)) throw new Error(`resource references are unsupported: ${path}`);
  if (/\{[^{}]*,\s*(?:plural|select|selectordinal)\s*,/i.test(decoded)) throw new Error(`complex ICU messages are unsupported: ${path}`);
  validateFormats(decoded, path);
  return decoded;
}

function validateFormats(value, path) {
  const types = new Map();
  let sequential = 0;
  let indexed = false;
  let unindexed = false;
  for (let i = 0; i < value.length; i++) {
    if (value[i] !== '%') continue;
    if (value[i + 1] === '%') { i++; continue; }
    const match = /^%(?:([1-9][0-9]*)\$)?([sd])/.exec(value.slice(i));
    if (!match) throw new Error(`unsupported string format near ${value.slice(i, i + 12)}: ${path}`);
    const position = match[1] ? Number(match[1]) : ++sequential;
    indexed ||= match[1] !== undefined;
    unindexed ||= match[1] === undefined;
    if (indexed && unindexed) throw new Error(`mixed indexed and unindexed string formats are unsupported: ${path}`);
    if (types.has(position) && types.get(position) !== match[2]) throw new Error(`conflicting format types at argument ${position}: ${path}`);
    types.set(position, match[2]);
    i += match[0].length - 1;
  }
}

function qualifier(directory) {
  if (directory === 'values') return 'base';
  const locale = /^values-([a-z]{2})(?:-r([A-Z]{2}))?$/.exec(directory);
  return locale ? locale[1] + (locale[2] ? `_${locale[2]}` : '') : null;
}

function propertyEscape(value, key = false) {
  let result = '';
  for (let i = 0; i < value.length; i++) {
    const char = value[i];
    if (char === '\\') result += '\\\\';
    else if (char === '\n') result += '\\n';
    else if (char === '\r') result += '\\r';
    else if (char === '\t') result += '\\t';
    else if (char === '=' || char === ':' || (char === ' ' && (key || i === 0)) || (key && (char === '#' || char === '!'))) result += `\\${char}`;
    else result += char;
  }
  return result;
}

function properties(entries) {
  return [...entries].sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${propertyEscape(key, true)}=${propertyEscape(String(value))}\n`).join('');
}

function parsedEntries(path, qualifierName, source, namespace) {
  const root = parseXml(path);
  const entries = [];
  for (const node of root.children) {
    let androidType = RESOURCE_TYPES.get(node.tag);
    if (node.tag === 'item') androidType = node.attrs.type === 'string' ? 'string' : null;
    if (!androidType) continue;
    const name = node.attrs.name ?? '';
    if (!/^[a-z_][a-z0-9_]*$/.test(name)) throw new Error(`Invalid Android ${node.tag} name ${name}: ${path}`);
    const symbol = `${namespace}.R.${androidType}.${name}`;
    try {
      let value;
      if (androidType === 'string') value = androidText(node, path);
      else if (androidType === 'plurals') {
        if (node.text.trim() || !node.children.length || node.children.some(item => item.tag !== 'item')) throw new Error(`invalid plurals structure: ${path}`);
        value = {};
        for (const item of node.children) {
          const quantity = item.attrs.quantity;
          if (!QUANTITIES.has(quantity) || value[quantity] !== undefined) throw new Error(`invalid or duplicate plural quantity ${quantity}: ${path}`);
          value[quantity] = androidText(item, path);
        }
        if (value.other === undefined) throw new Error(`plurals requires quantity other: ${path}`);
      } else {
        if (node.text.trim() || node.children.some(item => item.tag !== 'item')) throw new Error(`invalid string-array structure: ${path}`);
        value = node.children.map(item => androidText(item, path));
      }
      if (qualifierName === null) throw new Error(`unsupported values qualifier ${basename(dirname(path))}: ${path}`);
      entries.push({ symbol, androidType, qualifier: qualifierName, value, source, path, reason: null, shadowed: [] });
    } catch (error) {
      entries.push({ symbol, androidType, qualifier: qualifierName ?? `unsupported:${basename(dirname(path))}`, value: null,
        source, path, reason: error.message, shadowed: [] });
    }
  }
  return entries;
}

/** Materialize selected-variant Android values resources from ordered module roots. */
export function materializeProjectStrings({ resourceRoots, namespace, out, symbolsFile, variant }) {
  if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(namespace ?? '')) throw new Error('namespace must be an ASCII Java package name');
  if (!Array.isArray(resourceRoots) || !resourceRoots.length) throw new Error('Project string resources require ordered resource roots');
  if (!isAbsolute(out ?? '') || !isAbsolute(symbolsFile ?? '')) throw new Error('Project string output and symbols must be absolute paths');
  const destination = resolve(out);
  if (existsSync(destination)) throw new Error(`Output already exists: ${destination}`);
  const seenRoots = new Set();
  const roots = resourceRoots.map((root, index) => {
    if (!root || typeof root.sourceSet !== 'string' || !root.sourceSet || !Number.isInteger(root.overlayPriority) || root.overlayPriority < 0 || !isAbsolute(root.path ?? '')) {
      throw new Error(`Invalid project resource root at index ${index}`);
    }
    const path = resolve(root.path);
    const stat = lstatSync(path);
    if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error(`Project resource root must be a real directory: ${path}`);
    if (seenRoots.has(path)) throw new Error(`Duplicate project resource root: ${path}`);
    seenRoots.add(path);
    const nested = relative(path, destination);
    if (nested === '' || (!nested.startsWith(`..${sep}`) && nested !== '..' && !isAbsolute(nested))) throw new Error(`Project string output must not be inside resource root: ${path}`);
    return { sourceSet: root.sourceSet, overlayPriority: root.overlayPriority, path };
  });
  for (let i = 1; i < roots.length; i++) if (roots[i].overlayPriority < roots[i - 1].overlayPriority) {
    throw new Error('Project resource roots must be ordered from lower to higher overlay priority');
  }

  const ids = new Map();
  const idNumbers = new Set();
  for (const line of readFileSync(symbolsFile, 'utf8').split(/\r?\n/)) {
    const match = /^int\s+(string|plurals|array)\s+([a-z_][a-z0-9_]*)\s+(0x[0-9a-fA-F]+|\d+)\s*$/.exec(line);
    if (!match) continue;
    const symbol = `${namespace}.R.${match[1]}.${match[2]}`;
    const id = Number(match[3]);
    if (!Number.isInteger(id) || id <= 0 || id > 0x7fffffff || ids.has(symbol) || idNumbers.has(id)) throw new Error(`Invalid or duplicate selected-variant string ID: ${symbol}`);
    ids.set(symbol, id); idNumbers.add(id);
  }

  const selected = new Map();
  for (const root of roots) for (const directory of readdirSync(root.path).sort()) {
    if (!directory.startsWith('values')) continue;
    const folder = join(root.path, directory);
    const folderStat = lstatSync(folder);
    if (folderStat.isSymbolicLink() || !folderStat.isDirectory()) throw new Error(`Values resource directory must be real: ${folder}`);
    const source = { sourceSet: root.sourceSet, overlayPriority: root.overlayPriority };
    for (const file of readdirSync(folder).filter(name => name.endsWith('.xml')).sort()) {
      const path = join(folder, file);
      const stat = lstatSync(path);
      if (stat.isSymbolicLink() || !stat.isFile()) throw new Error(`Values resource must be a regular file: ${path}`);
      source.path = path;
      for (const candidate of parsedEntries(path, qualifier(directory), { ...source }, namespace)) {
        const key = `${candidate.qualifier}\u0000${candidate.symbol}`;
        const previous = selected.get(key);
        if (previous && previous.source.overlayPriority === root.overlayPriority) throw new Error(`Ambiguous project string resource ${candidate.symbol} for ${candidate.qualifier} at overlay priority ${root.overlayPriority}: ${previous.path} and ${path}`);
        if (previous && previous.source.overlayPriority > root.overlayPriority) continue;
        if (previous) candidate.shadowed = [previous.source, ...previous.shadowed];
        selected.set(key, candidate);
      }
    }
  }

  const bySymbol = new Map();
  for (const entry of selected.values()) {
    const values = bySymbol.get(entry.symbol) ?? [];
    values.push(entry); bySymbol.set(entry.symbol, values);
  }
  const supported = new Map();
  const unavailable = new Map();
  for (const [symbol, id] of ids) {
    const entries = bySymbol.get(symbol) ?? [];
    const base = entries.find(entry => entry.qualifier === 'base');
    const bad = entries.find(entry => entry.reason);
    const expectedType = /\.R\.(string|plurals|array)\./.exec(symbol)[1];
    if (!base) unavailable.set(symbol, { reason: `No default ${symbol} value exists in collected module resource roots`, entries });
    else if (base.androidType !== expectedType) unavailable.set(symbol, { reason: `Selected resource type does not match R.txt for ${symbol}`, entries });
    else if (bad) unavailable.set(symbol, { reason: bad.reason, entries });
    else supported.set(symbol, { id, entries: entries.filter(entry => entry.qualifier !== null) });
  }

  const stringPacks = new Map(), pluralPacks = new Map(), arrayPacks = new Map();
  const pack = (packs, qualifierName) => { if (!packs.has(qualifierName)) packs.set(qualifierName, new Map()); return packs.get(qualifierName); };
  for (const [symbol, item] of supported) for (const entry of item.entries) {
    if (entry.androidType === 'string') pack(stringPacks, entry.qualifier).set(symbol, entry.value);
    else if (entry.androidType === 'plurals') for (const [quantity, value] of Object.entries(entry.value)) pack(pluralPacks, entry.qualifier).set(`${symbol}.${quantity}`, value);
    else entry.value.forEach((value, index) => pack(arrayPacks, entry.qualifier).set(`${symbol}.${index}`, value));
  }

  mkdirSync(dirname(destination), { recursive: true });
  const stage = mkdtempSync(join(dirname(destination), `.${basename(destination)}-stage-`));
  let claimed = false;
  const published = [];
  try {
    for (const [qualifierName, values] of stringPacks) writeFileSync(join(stage, `${qualifierName}.properties`), properties(values), { flag: 'wx' });
    if (!stringPacks.has('base')) writeFileSync(join(stage, 'base.properties'), '', { flag: 'wx' });
    for (const [qualifierName, values] of pluralPacks) writeFileSync(join(stage, `plurals-${qualifierName}.properties`), properties(values), { flag: 'wx' });
    for (const [qualifierName, values] of arrayPacks) writeFileSync(join(stage, `arrays-${qualifierName}.properties`), properties(values), { flag: 'wx' });
    writeFileSync(join(stage, 'source-resource-ids.properties'), properties([...supported].map(([symbol, item]) => [symbol, item.id])), { flag: 'wx' });
    writeFileSync(join(stage, 'unsupported-string-resources.properties'), properties([...unavailable].map(([symbol, item]) => [symbol, Buffer.from(item.reason).toString('base64')])), { flag: 'wx' });
    writeFileSync(join(stage, 'unsupported-string-resource-ids.properties'), properties([...unavailable].map(([symbol, item]) =>
      [String(ids.get(symbol)), Buffer.from(`Unsupported Android values resource ${symbol}: ${item.reason}`).toString('base64')])), { flag: 'wx' });
    const provenance = { schemaVersion: 1, namespace, variant, roots, resources: [...ids.keys()].sort().map(symbol => {
      const item = supported.get(symbol) ?? unavailable.get(symbol);
      return { symbol, status: supported.has(symbol) ? 'materialized' : 'unsupported', ...(item.reason ? { reason: item.reason } : {}),
        variants: item.entries.map(entry => ({ qualifier: entry.qualifier, source: entry.source, shadowed: entry.shadowed })) };
    }) };
    writeFileSync(join(stage, 'string-resource-origins.json'), JSON.stringify(provenance, null, 2) + '\n', { flag: 'wx' });
    mkdirSync(destination); claimed = true;
    for (const name of readdirSync(stage)) { renameSync(join(stage, name), join(destination, name)); published.push(name); }
    return { output: destination, provenance: join(destination, 'string-resource-origins.json'), count: supported.size, unsupportedCount: unavailable.size };
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
      throw new Error('Usage: node string-resources.mjs --res-dir /android/res --namespace example --out /fresh/output --symbols /R.txt');
    }
    values[args[i]] = args[i + 1];
  }
  const root = resolve(values['--res-dir']);
  return materializeProjectStrings({ namespace: values['--namespace'], out: resolve(values['--out']), symbolsFile: resolve(values['--symbols']),
    variant: values['--variant'] ?? 'manual', resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: root }] });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.stdout.write(`${JSON.stringify(main(process.argv.slice(2)))}\n`); }
  catch (error) { process.stderr.write(`String resources: ${error.message}\n`); process.exitCode = 1; }
}
