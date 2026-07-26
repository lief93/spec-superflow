// ssf memories <init|list|check> [project-root] - manage shared auto memory
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, normalize, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ENTRYPOINT = 'MEMORY.md';
const MAX_ENTRY_LINES = 200;
const MAX_ENTRY_BYTES = 25_000;
const MAX_INDEX_ENTRY_LENGTH = 200;
const MEMORY_TYPES = new Set(['feedback', 'project', 'reference']);
const REQUIRED_FRONTMATTER = ['name', 'description', 'type', 'modified'];

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
  return relative(memoryDir, file).split(sep).join('/');
}

function parseFrontmatter(content) {
  const lines = content.split(/\r?\n/);
  if (lines[0] !== '---') return { attributes: {}, body: content, error: 'missing YAML frontmatter' };
  const end = lines.indexOf('---', 1);
  if (end === -1) return { attributes: {}, body: '', error: 'unclosed YAML frontmatter' };

  const attributes = {};
  for (const line of lines.slice(1, end)) {
    if (!line.trim()) continue;
    const match = /^([A-Za-z][A-Za-z0-9_-]*):\s*(.*?)\s*$/.exec(line);
    if (!match) return { attributes, body: lines.slice(end + 1).join('\n'), error: `unsupported frontmatter line: ${line}` };
    const [, key, rawValue] = match;
    attributes[key] = rawValue.replace(/^("|')(.*)\1$/, '$2');
  }
  return { attributes, body: lines.slice(end + 1).join('\n'), error: null };
}

function extractTopicLinks(content) {
  const links = [];
  const pattern = /\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)/g;
  let match;
  while ((match = pattern.exec(content)) !== null) {
    const target = match[1].trim().replace(/^\.\//, '');
    if (!target.includes('://') && !target.startsWith('/')) links.push(target);
  }
  return links;
}

function isSafeTopicPath(target) {
  const normalized = normalize(target).split(sep).join('/');
  return normalized !== '..' && !normalized.startsWith('../') && normalized !== ENTRYPOINT;
}

function isValidModified(value) {
  return /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)?$/.test(value) && !Number.isNaN(Date.parse(value));
}

function validateEntrypoint(content, issues) {
  const lines = content.split(/\r?\n/);
  const lineCount = lines.at(-1) === '' ? lines.length - 1 : lines.length;
  const byteCount = Buffer.byteLength(content, 'utf-8');
  if (lines[0] !== '# Project Memory') issues.push(`${ENTRYPOINT} must start with '# Project Memory'`);
  if (lineCount > MAX_ENTRY_LINES) issues.push(`${ENTRYPOINT} exceeds ${MAX_ENTRY_LINES} lines: ${lineCount}`);
  if (byteCount > MAX_ENTRY_BYTES) issues.push(`${ENTRYPOINT} exceeds 25,000 bytes: ${byteCount}`);

  for (const [index, line] of lines.entries()) {
    const trimmed = line.trim();
    if (!trimmed || (index === 0 && trimmed === '# Project Memory')) continue;
    if (!/^- \[[^\]]+\]\([^)]+\.md(?:#[^)]+)?\) - \S/.test(trimmed)) {
      issues.push(`${ENTRYPOINT} line ${index + 1} must be a one-line topic link with a relevance hook`);
    }
    if (trimmed.length > MAX_INDEX_ENTRY_LENGTH) {
      issues.push(`${ENTRYPOINT} line ${index + 1} exceeds ${MAX_INDEX_ENTRY_LENGTH} characters`);
    }
  }
}

function validateTopic(name, content, seenNames, issues) {
  const parsed = parseFrontmatter(content);
  if (parsed.error) {
    issues.push(`${name}: ${parsed.error}`);
    return;
  }

  for (const field of REQUIRED_FRONTMATTER) {
    if (!parsed.attributes[field]) issues.push(`${name}: missing frontmatter field '${field}'`);
  }
  if (parsed.attributes.type && !MEMORY_TYPES.has(parsed.attributes.type)) {
    issues.push(`${name}: unsupported memory type '${parsed.attributes.type}' (use feedback, project, or reference)`);
  }
  if (parsed.attributes.modified && !isValidModified(parsed.attributes.modified)) {
    issues.push(`${name}: modified must be YYYY-MM-DD or an ISO UTC timestamp`);
  }
  if (parsed.attributes.name) {
    const existing = seenNames.get(parsed.attributes.name);
    if (existing) issues.push(`${name}: duplicate memory name '${parsed.attributes.name}' also used by ${existing}`);
    else seenNames.set(parsed.attributes.name, name);
  }
  if (!parsed.body.trim()) issues.push(`${name}: topic body is empty`);
}

function resolveMemoryRoot(projectRoot) {
  return join(resolve(projectRoot), '.spec-superflow', 'memories');
}

function init(projectRoot) {
  const memoryDir = resolveMemoryRoot(projectRoot);
  const entrypoint = join(memoryDir, ENTRYPOINT);
  if (existsSync(entrypoint)) {
    console.log(`Shared auto memory already initialized: ${entrypoint}`);
    return 0;
  }

  const existing = collectMarkdown(memoryDir);
  if (existing.length > 0) {
    console.error('Existing Serena-style or unindexed memory detected. Use memory-manager to classify and migrate useful content before creating MEMORY.md.');
    return 1;
  }

  const template = join(__dirname, '..', '..', 'skills', 'memory-manager', 'references', ENTRYPOINT);
  mkdirSync(memoryDir, { recursive: true });
  writeFileSync(entrypoint, readFileSync(template, 'utf-8'));
  console.log(`Shared auto memory initialized: ${entrypoint}`);
  return 0;
}

function list(projectRoot) {
  const memoryDir = resolveMemoryRoot(projectRoot);
  const files = collectMarkdown(memoryDir);
  if (files.length === 0) {
    console.error(`No shared auto memory found at ${memoryDir}`);
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

  if (!names.has(ENTRYPOINT)) {
    issues.push(`Missing required shared-memory entrypoint: ${ENTRYPOINT}`);
  } else {
    const entry = readFileSync(join(memoryDir, ENTRYPOINT), 'utf-8');
    validateEntrypoint(entry, issues);

    const topicLinks = extractTopicLinks(entry);
    const linked = new Set(topicLinks);
    if (linked.size !== topicLinks.length) issues.push(`${ENTRYPOINT} contains duplicate topic links`);
    for (const target of linked) {
      if (!isSafeTopicPath(target)) issues.push(`Unsafe or invalid topic link in ${ENTRYPOINT}: ${target}`);
      else if (!names.has(target)) issues.push(`Broken topic link in ${ENTRYPOINT}: ${target}`);
    }
    for (const name of names) {
      if (name !== ENTRYPOINT && !linked.has(name)) issues.push(`Topic file is not indexed by ${ENTRYPOINT}: ${name}`);
    }
  }

  const seenNames = new Map();
  for (const file of files) {
    const name = memoryName(memoryDir, file);
    if (name !== ENTRYPOINT) validateTopic(name, readFileSync(file, 'utf-8'), seenNames, issues);
  }

  if (issues.length > 0) {
    console.error(`Shared auto-memory check failed (${issues.length} issue${issues.length === 1 ? '' : 's'}):`);
    for (const issue of issues) console.error(`- ${issue}`);
    return 1;
  }

  console.log(`Shared auto-memory check passed: ${files.length} file${files.length === 1 ? '' : 's'}, typed topics indexed within load limits.`);
  return 0;
}

export async function run(args) {
  const subcommand = args[0];
  const projectRoot = args[1] || process.cwd();

  if (subcommand === 'init') process.exitCode = init(projectRoot);
  else if (subcommand === 'list') process.exitCode = list(projectRoot);
  else if (subcommand === 'check') process.exitCode = check(projectRoot);
  else {
    console.log('Usage: ssf memories <init|list|check> [project-root]');
    process.exitCode = subcommand ? 2 : 0;
  }
}

export {
  ENTRYPOINT,
  MAX_ENTRY_BYTES,
  MAX_ENTRY_LINES,
  MEMORY_TYPES,
  check,
  collectMarkdown,
  extractTopicLinks,
  init,
  isValidModified,
  list,
  memoryName,
  parseFrontmatter,
};
