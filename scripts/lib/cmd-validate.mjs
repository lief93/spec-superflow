// ssf validate <dir> — validate artifacts in a change directory
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join, basename, relative } from 'node:path';

async function getValidator() {
  const mod = await import('../../dist/index.js');
  return new mod.Validator(false);
}

function findFiles(dir, pattern) {
  const results = [];
  if (!existsSync(dir)) return results;
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) results.push(...findFiles(full, pattern));
    else if (st.isFile() && pattern.test(entry)) results.push(full);
  }
  return results;
}

function makeReport(issues) {
  return {
    valid: issues.filter(i => i.level === 'ERROR').length === 0,
    issues,
    summary: {
      errors: issues.filter(i => i.level === 'ERROR').length,
      warnings: issues.filter(i => i.level === 'WARNING').length,
      info: issues.filter(i => i.level === 'INFO').length,
    },
  };
}

function extractRequirementNames(content) {
  const names = [];
  const regex = /^###\s*Requirement:\s*(.+?)\s*$/gim;
  let match;
  while ((match = regex.exec(content)) !== null) {
    names.push(match[1].trim());
  }
  return names;
}

function hasSection(content, title) {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  return new RegExp(`^##\\s+.*${escaped}.*$`, 'im').test(content);
}

function extractSection(content, title) {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  const heading = new RegExp(`^##\\s+.*${escaped}.*$`, 'im');
  const match = heading.exec(content);
  if (!match) return null;

  const start = match.index + match[0].length;
  const rest = content.slice(start);
  const next = rest.search(/^##\s+/m);
  return (next === -1 ? rest : rest.slice(0, next)).trim();
}

function normalizeCell(value) {
  return String(value || '')
    .replace(/\\\|/g, '|')
    .replace(/[`*_]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeRequirementName(value) {
  return normalizeCell(value).toLowerCase();
}

function isMeaningfulCell(value) {
  const normalized = normalizeCell(value).toLowerCase();
  return normalized !== '' && !['-', '—', 'n/a', 'na', 'none', 'tbd', 'todo', 'pending'].includes(normalized);
}

function splitMarkdownTableRow(line) {
  const trimmed = line.trim();
  if (!trimmed.startsWith('|')) return null;
  return trimmed
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(normalizeCell);
}

function isTableDelimiter(cells) {
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, '')));
}

function normalizeHeader(value) {
  return normalizeCell(value).toLowerCase().replace(/s$/, '');
}

function parseTraceabilityTable(sectionContent) {
  const lines = sectionContent.split('\n').map(line => line.trim()).filter(Boolean);

  for (let i = 0; i < lines.length - 1; i++) {
    const headerCells = splitMarkdownTableRow(lines[i]);
    const delimiterCells = splitMarkdownTableRow(lines[i + 1]);
    if (!headerCells || !delimiterCells || !isTableDelimiter(delimiterCells)) continue;

    const headers = headerCells.map(normalizeHeader);
    const requiredHeaders = ['requirement', 'approved behavior', 'test obligation', 'batch'];
    const indexes = {};
    for (const required of requiredHeaders) {
      const idx = headers.indexOf(required);
      if (idx === -1) return { error: `Requirement Traceability table must include columns: ${requiredHeaders.join(', ')}` };
      indexes[required] = idx;
    }

    const rows = [];
    for (let j = i + 2; j < lines.length; j++) {
      const cells = splitMarkdownTableRow(lines[j]);
      if (!cells) break;
      rows.push({
        requirement: cells[indexes.requirement] || '',
        approvedBehavior: cells[indexes['approved behavior']] || '',
        testObligation: cells[indexes['test obligation']] || '',
        batch: cells[indexes.batch] || '',
      });
    }
    return { rows };
  }

  return { error: 'Requirement Traceability section must contain a markdown table' };
}

function extractBatchNames(contractContent) {
  const section = extractSection(contractContent, 'Task Batches') || '';
  const names = new Set();
  const regex = /^###\s*(Batch\s+\d+)/gim;
  let match;
  while ((match = regex.exec(section)) !== null) {
    names.add(match[1].toLowerCase());
  }
  return names;
}

function referencedBatches(value) {
  const names = [];
  const regex = /\bBatch\s+\d+\b/gi;
  let match;
  while ((match = regex.exec(value)) !== null) {
    names.push(match[0].toLowerCase());
  }
  return names;
}

function validateSpecsLayout(changeDir, specsDir, specFiles) {
  const mdFiles = findFiles(specsDir, /\.md$/);
  const issues = [];

  for (const mdFile of mdFiles) {
    if (basename(mdFile) !== 'spec.md') {
      issues.push({
        level: 'ERROR',
        path: relative(changeDir, mdFile),
        message: 'Spec files must be named spec.md inside a capability directory, for example specs/rate-limit/spec.md',
      });
    }
  }

  if (specFiles.length === 0) {
    issues.push({
      level: 'ERROR',
      path: 'specs/',
      message: 'No specs/**/spec.md files found',
    });
  }

  return makeReport(issues);
}

function validateExecutionContract(contractContent, requirementNames) {
  const requiredSections = [
    'Intent Lock',
    'Approved Behavior',
    'Requirement Traceability',
    'Design Constraints',
    'Task Batches',
    'Test Obligations',
    'Review Gates',
    'Escalation Rules',
  ];
  const recommendedSections = ['Execution Mode', 'Verification Dimensions'];
  const issues = [];

  for (const section of requiredSections) {
    if (!hasSection(contractContent, section)) {
      issues.push({
        level: 'ERROR',
        path: 'execution-contract.md',
        message: `Missing required section: ## ${section}`,
      });
    }
  }

  for (const section of recommendedSections) {
    if (!hasSection(contractContent, section)) {
      issues.push({
        level: 'WARNING',
        path: 'execution-contract.md',
        message: `Missing recommended section from template: ## ${section}`,
      });
    }
  }

  const traceabilitySection = extractSection(contractContent, 'Requirement Traceability');
  if (!traceabilitySection) {
    issues.push({
      level: 'ERROR',
      path: 'execution-contract.md',
      message: 'Missing Requirement Traceability table. Regenerate execution-contract.md with contract-builder so every spec requirement maps to behavior, tests, and batches.',
    });
    return makeReport(issues);
  }

  const table = parseTraceabilityTable(traceabilitySection);
  if (table.error) {
    issues.push({
      level: 'ERROR',
      path: 'execution-contract.md',
      message: table.error,
    });
    return makeReport(issues);
  }

  const batchNames = extractBatchNames(contractContent);
  const rowsByRequirement = new Map();
  for (const row of table.rows) {
    const key = normalizeRequirementName(row.requirement);
    if (!key) continue;
    if (rowsByRequirement.has(key)) {
      issues.push({
        level: 'ERROR',
        path: 'execution-contract.md',
        message: `Duplicate Requirement Traceability row: ${row.requirement}`,
      });
      continue;
    }
    rowsByRequirement.set(key, row);
  }

  for (const requirementName of requirementNames) {
    const row = rowsByRequirement.get(normalizeRequirementName(requirementName));
    if (!row) {
      issues.push({
        level: 'ERROR',
        path: 'execution-contract.md',
        message: `Requirement missing from traceability table: ${requirementName}`,
      });
      continue;
    }

    if (!isMeaningfulCell(row.approvedBehavior)) {
      issues.push({
        level: 'ERROR',
        path: 'execution-contract.md',
        message: `Traceability row for "${requirementName}" must map to non-empty Approved Behavior`,
      });
    }
    if (!isMeaningfulCell(row.testObligation)) {
      issues.push({
        level: 'ERROR',
        path: 'execution-contract.md',
        message: `Traceability row for "${requirementName}" must map to non-empty Test Obligation`,
      });
    }

    const batches = referencedBatches(row.batch);
    if (batches.length === 0) {
      issues.push({
        level: 'ERROR',
        path: 'execution-contract.md',
        message: `Traceability row for "${requirementName}" must reference at least one Task Batches heading such as Batch 1`,
      });
    }
    for (const batch of batches) {
      if (!batchNames.has(batch)) {
        issues.push({
          level: 'ERROR',
          path: 'execution-contract.md',
          message: `Traceability row for "${requirementName}" references missing task batch: ${batch}`,
        });
      }
    }
  }

  for (const row of table.rows) {
    const key = normalizeRequirementName(row.requirement);
    if (key && !requirementNames.some(name => normalizeRequirementName(name) === key)) {
      issues.push({
        level: 'WARNING',
        path: 'execution-contract.md',
        message: `Traceability row has no matching spec requirement: ${row.requirement}`,
      });
    }
  }

  return makeReport(issues);
}

function printReport(label, report) {
  console.log(`\n  📋 ${label}`);
  if (report.valid) {
    console.log(`     ✅ valid (${report.summary.errors} errors, ${report.summary.warnings} warnings, ${report.summary.info} info)`);
  } else {
    console.log(`     ❌ invalid (${report.summary.errors} errors, ${report.summary.warnings} warnings, ${report.summary.info} info)`);
  }
  for (const issue of report.issues) {
    const icon = issue.level === 'ERROR' ? '🔴' : issue.level === 'WARNING' ? '🟡' : '🔵';
    console.log(`     ${icon} [${issue.level}] ${issue.path}: ${issue.message}`);
  }
}

export async function run(args) {
  if (args.length < 1) {
    console.error('Usage: ssf validate <change-dir>');
    process.exit(2);
  }

  const changeDir = args[0];
  if (!existsSync(changeDir) || !statSync(changeDir).isDirectory()) {
    console.error(`Error: "${changeDir}" is not a valid directory`);
    process.exit(2);
  }

  const changeName = basename(changeDir);
  const validator = await getValidator();

  console.log(`🔍 Validating: ${changeDir}`);
  console.log(`   Change: ${changeName}`);

  let hasErrors = false;

  // Validate proposal.md
  const proposalPath = join(changeDir, 'proposal.md');
  if (existsSync(proposalPath)) {
    const content = readFileSync(proposalPath, 'utf-8');
    const report = validator.validateChangeContent(changeName, content);
    printReport('proposal.md', report);
    if (!report.valid) hasErrors = true;
  }

  // Validate specs/*/spec.md
  const specsDir = join(changeDir, 'specs');
  const requirementNames = [];
  if (existsSync(specsDir)) {
    const specFiles = findFiles(specsDir, /^spec\.md$/);
    const layoutReport = validateSpecsLayout(changeDir, specsDir, specFiles);
    if (layoutReport.issues.length > 0) {
      printReport('specs/ layout', layoutReport);
      if (!layoutReport.valid) hasErrors = true;
    }
    for (const specFile of specFiles) {
      const content = readFileSync(specFile, 'utf-8');
      const report = validator.validateDeltaSpec(content);
      const rel = relative(changeDir, specFile);
      printReport(rel, report);
      if (!report.valid) hasErrors = true;
      requirementNames.push(...extractRequirementNames(content));
    }
  }

  const contractPath = join(changeDir, 'execution-contract.md');
  if (existsSync(contractPath)) {
    const content = readFileSync(contractPath, 'utf-8');
    const report = validateExecutionContract(content, requirementNames);
    printReport('execution-contract.md', report);
    if (!report.valid) hasErrors = true;
  }

  // Basic structural validation for design.md and tasks.md (shared pattern)
  const STRUCTURAL_CHECKS = [
    { file: 'design.md', errorMsg: 'design.md is too short (< 50 chars) — provide architecture decisions, trade-offs, and data flow', warningMsg: 'design.md has no section headings — consider adding ## Architecture, ## Data Flow, ## Error Handling' },
    { file: 'tasks.md', errorMsg: 'tasks.md is too short (< 50 chars) — provide actionable, ordered implementation tasks', warningMsg: 'tasks.md has no section headings — consider adding ## File Structure and ## Tasks' },
  ];

  for (const { file, errorMsg, warningMsg } of STRUCTURAL_CHECKS) {
    const filePath = join(changeDir, file);
    if (!existsSync(filePath)) continue;

    const content = readFileSync(filePath, 'utf-8').trim();
    const issues = [];
    if (content.length < 50) issues.push({ level: 'ERROR', path: file, message: errorMsg });
    if (!content.includes('##')) issues.push({ level: 'WARNING', path: file, message: warningMsg });
    const report = {
      valid: issues.filter(i => i.level === 'ERROR').length === 0,
      issues,
      summary: { errors: issues.filter(i => i.level === 'ERROR').length, warnings: issues.filter(i => i.level === 'WARNING').length, info: 0 },
    };
    printReport(file, report);
    if (!report.valid) hasErrors = true;
  }

  console.log('');
  if (hasErrors) {
    console.log('❌ Validation failed with errors.');
    process.exit(1);
  } else {
    console.log('✅ All artifacts validated.');
    process.exit(0);
  }
}
