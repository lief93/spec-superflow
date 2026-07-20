// ssf memories <subcommand> [project-root] — inspect and validate no-MCP project memories
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';

function collectMarkdown(dir) {
  if (!existsSync(dir)) return [];
  const files = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) files.push(...collectMarkdown(full));
    else if (stat.isFile() && entry.endsWith('.md')) files.push(full);
  }
  return files.sort();
}

function memoryName(memoryDir, file) {
  return relative(memoryDir, file).split(sep).join('/').replace(/\.md$/, '');
}

function extractReferences(content) {
  const references = [];
  const pattern = /`mem:([A-Za-z0-9_\-/]+)`/g;
  let match;
  while ((match = pattern.exec(content)) !== null) references.push(match[1]);
  return references;
}

function resolveMemoryRoot(projectRoot) {
  return join(resolve(projectRoot), '.spec-superflow', 'memories');
}

function list(projectRoot) {
  const memoryDir = resolveMemoryRoot(projectRoot);
  const files = collectMarkdown(memoryDir);
  if (files.length === 0) {
    console.error(`No memories found at ${memoryDir}`);
    return 1;
  }
  for (const file of files) console.log(memoryName(memoryDir, file));
  return 0;
}

function check(projectRoot) {
  const memoryDir = resolveMemoryRoot(projectRoot);
  const files = collectMarkdown(memoryDir);
  const names = new Set(files.map(file => memoryName(memoryDir, file)));
  const issues = [];

  if (!names.has('memory_maintenance')) issues.push('Missing required memory: memory_maintenance');
  if (!names.has('core')) issues.push('Missing required graph root: core');

  for (const file of files) {
    const source = memoryName(memoryDir, file);
    if (source === 'memory_maintenance') continue;
    for (const target of extractReferences(readFileSync(file, 'utf-8'))) {
      if (!names.has(target)) issues.push(`Broken reference in ${source}: mem:${target}`);
    }
  }

  if (issues.length > 0) {
    console.error(`Memory check failed (${issues.length} issue${issues.length === 1 ? '' : 's'}):`);
    for (const issue of issues) console.error(`- ${issue}`);
    return 1;
  }

  console.log(`Memory check passed: ${files.length} memories, no broken references.`);
  return 0;
}

export async function run(args) {
  const subcommand = args[0];
  const projectRoot = args[1] || process.cwd();

  if (subcommand === 'list') {
    process.exitCode = list(projectRoot);
    return;
  }
  if (subcommand === 'check') {
    process.exitCode = check(projectRoot);
    return;
  }

  console.log('Usage: ssf memories <list|check> [project-root]');
  process.exitCode = subcommand ? 2 : 0;
}

export { collectMarkdown, extractReferences, memoryName, check, list };
