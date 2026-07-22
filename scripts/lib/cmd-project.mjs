// ssf project check [project-root] — validate generated project baseline documents
import { existsSync, readFileSync } from 'node:fs';
import { extname, join, resolve } from 'node:path';

const GUIDELINE = 'docs/project/project-guidelines.md';
const INSTRUCTIONS = '.github/copilot-instructions.md';
const REQUIRED_HEADINGS = [
  '# 项目开发基线',
  '## 技术与框架约束',
  '## 架构与编码规则',
  '## 经典实现索引',
];
const RECIPE_FIELDS = ['适用条件', '新建或修改', '实现顺序', '必须保持', '完成标准', '参考实现'];
const SOURCE_EXTENSIONS = new Set([
  '.c', '.cc', '.cpp', '.cs', '.ets', '.go', '.gradle', '.h', '.hpp', '.java', '.js',
  '.json', '.json5', '.kt', '.kts', '.md', '.mjs', '.mm', '.properties', '.py', '.rs',
  '.swift', '.toml', '.ts', '.tsx', '.vue', '.xml', '.yaml', '.yml',
]);

function extractInlineCode(markdown) {
  return [...markdown.matchAll(/`([^`\n]+)`/g)].map(match => match[1].trim());
}

function parseReference(token) {
  if (token.includes('<') || token.includes('...') || token.includes('*')) return null;
  const first = token.split(/[;,]/, 1)[0].trim();
  const [file, symbol] = first.split('#', 2);
  if (!SOURCE_EXTENSIONS.has(extname(file))) return null;
  return { token, file: file.replace(/^\.\//, ''), symbol: symbol?.replace(/\(.*\)$/, '') };
}

function check(projectRoot) {
  const root = resolve(projectRoot);
  const guidelinePath = join(root, GUIDELINE);
  const instructionPath = join(root, INSTRUCTIONS);
  const issues = [];
  let checkedPaths = 0;
  let checkedSymbols = 0;

  for (const file of [INSTRUCTIONS, GUIDELINE]) {
    if (!existsSync(join(root, file))) issues.push(`Missing required file: ${file}`);
  }
  if (issues.length > 0) return { root, issues, checkedPaths, checkedSymbols };

  const instructions = readFileSync(instructionPath, 'utf-8');
  const guideline = readFileSync(guidelinePath, 'utf-8');
  if (!instructions.includes(GUIDELINE)) {
    issues.push(`${INSTRUCTIONS} must direct the agent to ${GUIDELINE}`);
  }

  const headings = new Set(guideline.split('\n').filter(line => /^#{1,3} /.test(line.trim())).map(line => line.trim()));
  for (const heading of REQUIRED_HEADINGS) {
    if (!headings.has(heading)) issues.push(`Missing heading in ${GUIDELINE}: ${heading}`);
  }

  const placeholders = [...`${instructions}\n${guideline}`.matchAll(/<([a-z][^>\n]*)>/gi)].map(match => match[0]);
  for (const placeholder of placeholders) issues.push(`Unresolved placeholder: ${placeholder}`);

  const recipeBlocks = guideline.split(/^### /m).slice(1);
  if (recipeBlocks.length === 0) issues.push(`${GUIDELINE} must contain at least one classic implementation recipe`);
  for (const block of recipeBlocks) {
    const title = block.split('\n', 1)[0].trim();
    for (const field of RECIPE_FIELDS) {
      if (!block.includes(`- ${field}：`)) issues.push(`Recipe "${title}" missing field: ${field}`);
    }
  }

  for (const token of extractInlineCode(guideline)) {
    const reference = parseReference(token);
    if (!reference) continue;
    checkedPaths += 1;
    const sourcePath = join(root, reference.file);
    if (!existsSync(sourcePath)) {
      issues.push(`Missing referenced path: ${reference.token}`);
      continue;
    }
    if (reference.symbol) {
      checkedSymbols += 1;
      const symbol = reference.symbol.split('.').at(-1);
      if (!readFileSync(sourcePath, 'utf-8').includes(symbol)) {
        issues.push(`Missing referenced symbol: ${reference.token}`);
      }
    }
  }

  return { root, issues, checkedPaths, checkedSymbols };
}

export async function run(args) {
  const subcommand = args[0];
  const projectRoot = args[1] || process.cwd();
  if (subcommand !== 'check') {
    console.log('Usage: ssf project check [project-root]');
    process.exitCode = subcommand ? 2 : 0;
    return;
  }

  const result = check(projectRoot);
  if (result.issues.length > 0) {
    console.error(`Project baseline check failed (${result.issues.length} issues):`);
    for (const issue of result.issues) console.error(`- ${issue}`);
    process.exitCode = 1;
    return;
  }
  console.log(`Project baseline check passed: ${result.checkedPaths} paths and ${result.checkedSymbols} symbols verified.`);
}

export { check, extractInlineCode, parseReference };
