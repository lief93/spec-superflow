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

export function materializeImages({ resDir, namespace, out }) {
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
  for (const directory of readdirSync(source).sort()) {
    if (directory !== 'drawable' && !directory.startsWith('drawable-')) continue;
    const folder = join(source, directory);
    const folderStat = lstatSync(folder);
    if (folderStat.isSymbolicLink() || !folderStat.isDirectory()) throw new Error(`Drawable directory is not a real directory (symlink unsupported): ${folder}`);
    const names = readdirSync(folder).sort();
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
  if (!entries.length) throw new Error(`No supported drawable resources found: ${source}`);
  mkdirSync(dirname(destination), { recursive: true });
  const stage = mkdtempSync(join(dirname(destination), `.${basename(destination)}-stage-`));
  let claimed = false;
  let mediaPublished = false;
  try {
    mkdirSync(join(stage, 'media'));
    for (const entry of entries) {
      const extension = entry.extension === '.xml' ? '.svg' : entry.extension === '.jpeg' ? '.jpg' : entry.extension;
      const bytes = entry.extension === '.xml' ? convertVector(entry.path) : bitmap(entry.path, entry.extension);
      writeFileSync(join(stage, 'media', `${entry.target}${extension}`), bytes, { flag: 'wx' });
    }
    const properties = entries.map(entry => `${entry.symbol} = ${entry.target}\n`).join('');
    writeFileSync(join(stage, 'image-resources.properties'), properties, { encoding: 'ascii', flag: 'wx' });
    // Exclusive mkdir prevents overwriting even an empty existing directory.
    // The complete mapping is the last publication step, never a partial map.
    mkdirSync(destination);
    claimed = true;
    renameSync(join(stage, 'media'), join(destination, 'media'));
    mediaPublished = true;
    renameSync(join(stage, 'image-resources.properties'), join(destination, 'image-resources.properties'));
    return { output: destination, properties: join(destination, 'image-resources.properties'), count: entries.length };
  } catch (error) {
    if (mediaPublished) rmSync(join(destination, 'media'), { recursive: true, force: true });
    if (claimed) {
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
    if (!['--res-dir', '--namespace', '--out'].includes(key) || values[key] !== undefined || !args[i + 1]) {
      throw new Error('Usage: node image-resources.mjs --res-dir /android/res --namespace example --out /fresh/output');
    }
    values[key] = args[i + 1];
  }
  return materializeImages({ resDir: values['--res-dir'], namespace: values['--namespace'], out: values['--out'] });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.stdout.write(`${JSON.stringify(main(process.argv.slice(2)))}\n`); }
  catch (error) { process.stderr.write(`Image resources: ${error.message}\n`); process.exitCode = 1; }
}
