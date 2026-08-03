// ssf validate <dir> — validate artifacts in a change directory
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join, basename, dirname, extname, relative, resolve, sep, posix } from 'node:path';

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

function extractRequirementScenarioPairs(content) {
  const pairs = [];
  let requirement = null;
  for (const line of content.split('\n')) {
    const requirementMatch = line.match(/^###\s*Requirement:\s*(.+?)\s*$/i);
    if (requirementMatch) {
      requirement = requirementMatch[1].trim();
      continue;
    }
    const scenarioMatch = line.match(/^####\s*Scenario:\s*(.+?)\s*$/i);
    if (requirement && scenarioMatch) {
      pairs.push({ requirement, scenario: scenarioMatch[1].trim() });
    }
  }
  return pairs;
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
    .replace(/[`*]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeRequirementName(value) {
  return normalizeCell(value).toLowerCase();
}

function normalizeDecisionName(value) {
  return normalizeCell(value).replace(/^decision\s*:\s*/i, '').toLowerCase();
}

function isMeaningfulCell(value) {
  const normalized = normalizeCell(value).toLowerCase();
  return normalized !== '' && !['-', '—', 'n/a', 'na', 'none', 'tbd', 'todo', 'pending'].includes(normalized);
}

const TEST_SOURCE_EXTENSIONS = new Set([
  '.c', '.cc', '.cjs', '.cpp', '.cs', '.dart', '.ets', '.feature', '.go', '.java', '.js', '.jsx',
  '.kt', '.kts', '.m', '.mm', '.php', '.py', '.rb', '.rs', '.swift', '.ts', '.tsx',
  '.mjs',
]);

function findProjectRoot(startDir) {
  let current = resolve(startDir);
  while (true) {
    if (existsSync(join(current, '.git'))) return current;
    const parent = dirname(current);
    if (parent === current) return null;
    current = parent;
  }
}

function isProjectRelativePath(filePath) {
  if (!filePath || filePath.startsWith('/') || filePath.startsWith('~') || /^[A-Za-z]:[\\/]/.test(filePath)) return false;
  return !filePath.replace(/\\/g, '/').split('/').includes('..');
}

function isTestSourcePath(filePath) {
  const slashPath = filePath.replace(/\\/g, '/');
  const normalized = slashPath.toLowerCase();
  const fileName = basename(slashPath);
  if (/(^|\/)(docs?|specs?|changes|\.spec-superflow)(\/|$)/.test(normalized)) return false;
  const hasTestRoot = /(^|\/)(test|tests|__tests__|androidtest|ohostest|uitests?|e2e|cypress|playwright|integration_test)(\/|$)/.test(normalized);
  const hasTestName = /\.(test|spec)\.[^.]+$/i.test(fileName)
    || /(?:Test|Tests|UITest)\.[^.]+$/.test(fileName)
    || /^(test_|tests_)/i.test(fileName)
    || /(^|[_-])(test|tests)\.[^.]+$/i.test(fileName);
  return TEST_SOURCE_EXTENSIONS.has(extname(normalized)) && (hasTestRoot || hasTestName);
}

function uiTestMatchesPlatform(platform, filePath) {
  const normalizedPlatform = normalizeRequirementName(platform);
  const normalizedPath = filePath.replace(/\\/g, '/').toLowerCase();
  if (normalizedPlatform.includes('android')) {
    return /(^|\/)src\/androidtest\//.test(normalizedPath);
  }
  if (/(harmony|openharmony|ohos)/.test(normalizedPlatform)) {
    return /(^|\/)src\/ohostest\//.test(normalizedPath);
  }
  if (/(^|\s)(ios|ipados|macos)(\s|$)/.test(normalizedPlatform)) {
    return /(^|\/)[^/]*uitests?\//.test(normalizedPath) || /uitests?\.[^.]+$/.test(normalizedPath);
  }
  if (/(web|browser)/.test(normalizedPlatform)) {
    return /(^|\/)(e2e|cypress|playwright)(\/|$)/.test(normalizedPath) || /\.(spec|test)\.[^.]+$/.test(normalizedPath);
  }
  return isTestSourcePath(filePath);
}

function isConcreteTestCase(value) {
  const normalized = normalizeCell(value).toLowerCase();
  if (normalized.length < 4) return false;
  return ![
    'all tests', 'all ui tests', 'related tests', 'regression tests', 'smoke tests',
    'test suite', 'ui test', 'device test', '相关测试', '回归测试', '冒烟测试', '全部测试',
  ].includes(normalized);
}

function isConcreteProof(value) {
  const normalized = normalizeCell(value).toLowerCase();
  const minimumLength = /[\u3400-\u9fff]/.test(normalized) ? 6 : 12;
  if (normalized.length < minimumLength) return false;
  return !/^(covers?|verifies?|tests?)\s+(the\s+)?(ac|scenario|requirement|behavior)\.?$/.test(normalized)
    && !/^(覆盖|验证|测试)(当前)?(ac|需求|场景|功能)(即可|通过|成功|正常)?[。.]?$/.test(normalized);
}

function validateTestPlanRow(rowName, row, projectRoot) {
  const issues = [];
  const layer = normalizeRequirementName(row.layer);
  const action = normalizeRequirementName(row.action);
  const testFile = normalizeCell(row['test file']);
  const testCase = normalizeCell(row['test case']);
  const unavailable = action === 'unavailable';

  if (!isMeaningfulCell(row.platform)) {
    issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} requires a concrete Platform` });
  }
  if (unavailable) {
    if (normalizeRequirementName(testFile) !== 'not configured') {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} Unavailable must use Test File "Not configured", not a document or source file` });
    }
    if (!isConcreteTestCase(testCase)) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} Unavailable requires the searched test roots/configuration and concrete capability gap in Test Case` });
    }
  } else {
    if (!isProjectRelativePath(testFile)) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} Test File must be one project-relative path` });
    } else if (testFile.includes('#')) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} must put the file path in Test File and the test method/title in Test Case` });
    } else if (!isTestSourcePath(testFile)) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} Test File must be a platform test source file, not documentation, production source, a command, or a regression-set label` });
    } else if (layer === 'ui' && !uiTestMatchesPlatform(row.platform, testFile)) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} UI Test File does not match the declared platform test location` });
    }

    if (!isConcreteTestCase(testCase)) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} requires one exact test method or test title in Test Case` });
    }

    if (['update', 'run existing'].includes(action) && isProjectRelativePath(testFile) && projectRoot) {
      const absolutePath = resolve(projectRoot, testFile);
      const insideProject = absolutePath === projectRoot || absolutePath.startsWith(`${projectRoot}${sep}`);
      if (!insideProject || !existsSync(absolutePath) || !statSync(absolutePath).isFile()) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} ${row.action} requires an existing test file: ${testFile}` });
      } else if (isConcreteTestCase(testCase) && !readFileSync(absolutePath, 'utf-8').includes(testCase)) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} Test Case was not found in existing test file: ${testCase}` });
      }
    } else if (['update', 'run existing'].includes(action) && !projectRoot) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} cannot verify an existing test file because no Git project root was found` });
    }
  }

  if (!isConcreteProof(row.prove)) {
    issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} Proves must state the observable AC outcome asserted by this test` });
  }
  return issues;
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

function parseMarkdownTable(sectionContent, requiredHeaders, tableName = 'Markdown') {
  const lines = sectionContent.split('\n').map(line => line.trim()).filter(Boolean);

  for (let i = 0; i < lines.length - 1; i++) {
    const headerCells = splitMarkdownTableRow(lines[i]);
    const delimiterCells = splitMarkdownTableRow(lines[i + 1]);
    if (!headerCells || !delimiterCells || !isTableDelimiter(delimiterCells)) continue;

    const headers = headerCells.map(normalizeHeader);
    const indexes = {};
    for (const required of requiredHeaders) {
      const idx = headers.indexOf(required);
      if (idx === -1) return { error: `${tableName} table must include columns: ${requiredHeaders.join(', ')}` };
      indexes[required] = idx;
    }

    const rows = [];
    for (let j = i + 2; j < lines.length; j++) {
      const cells = splitMarkdownTableRow(lines[j]);
      if (!cells) break;
      const row = {};
      for (const required of requiredHeaders) row[required] = cells[indexes[required]] || '';
      rows.push(row);
    }
    return { rows };
  }

  return { error: `${tableName} section must contain a markdown table` };
}

function parseTraceabilityTable(sectionContent) {
  const parsed = parseMarkdownTable(sectionContent, ['requirement', 'approved behavior', 'test obligation', 'batch'], 'Requirement Traceability');
  if (parsed.error) return parsed;
  return {
    rows: parsed.rows.map(row => ({
      requirement: row.requirement,
      approvedBehavior: row['approved behavior'],
      testObligation: row['test obligation'],
      batch: row.batch,
    })),
  };
}

const AC_TEST_MATRIX_HEADERS = ['requirement', 'ac', 'layer', 'platform', 'action', 'test file', 'test case', 'prove'];

function testRowKey(row) {
  return AC_TEST_MATRIX_HEADERS.map(header => normalizeRequirementName(row[header])).join('\u0000');
}

function exactTestCaseOwnershipKey(row) {
  const testFile = posix.normalize(
    normalizeCell(row['test file']).replace(/\\/g, '/'),
  ).toLowerCase();
  const testCase = normalizeRequirementName(row['test case']);
  return `${testFile}\u0000${testCase}`;
}

function validateAcTestMatrix(contractContent, taskTestRows) {
  const issues = [];
  const section = extractSection(contractContent, 'AC Test Matrix');
  if (!section) {
    issues.push({ level: 'ERROR', path: 'execution-contract.md', message: 'Missing ## AC Test Matrix copied from tasks.md' });
    return issues;
  }
  const parsed = parseMarkdownTable(section, AC_TEST_MATRIX_HEADERS, 'AC Test Matrix');
  if (parsed.error) {
    issues.push({ level: 'ERROR', path: 'execution-contract.md', message: parsed.error });
    return issues;
  }

  const planned = new Map();
  for (const row of taskTestRows) {
    const key = testRowKey(row);
    if (planned.has(key)) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `Duplicate AC test obligation: ${row.requirement} / ${row.ac} / ${row['test file']} / ${row['test case']}` });
    }
    planned.set(key, row);
  }
  const contracted = new Map();
  for (const row of parsed.rows) {
    const key = testRowKey(row);
    if (contracted.has(key)) {
      issues.push({ level: 'ERROR', path: 'execution-contract.md', message: `Duplicate AC Test Matrix row: ${row.requirement} / ${row.ac} / ${row['test file']} / ${row['test case']}` });
    }
    contracted.set(key, row);
  }

  for (const [key, row] of planned) {
    if (!contracted.has(key)) {
      issues.push({ level: 'ERROR', path: 'execution-contract.md', message: `AC Test Matrix is missing tasks.md obligation: ${row.requirement} / ${row.ac} / ${row['test file']} / ${row['test case']}` });
    }
  }
  for (const [key, row] of contracted) {
    if (!planned.has(key)) {
      issues.push({ level: 'ERROR', path: 'execution-contract.md', message: `AC Test Matrix row has no exact tasks.md obligation: ${row.requirement} / ${row.ac} / ${row['test file']} / ${row['test case']}` });
    }
  }
  return issues;
}

function coverageKey(requirement, scenario) {
  return `${normalizeRequirementName(requirement)}\u0000${normalizeRequirementName(scenario)}`;
}

function extractNestedSection(content, title, level) {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  const hashes = '#'.repeat(level);
  const heading = new RegExp(`^${hashes}\\s+${escaped}\\s*$`, 'im');
  const match = heading.exec(content);
  if (!match) return null;
  const start = match.index + match[0].length;
  const rest = content.slice(start);
  const next = rest.search(new RegExp(`^#{1,${level}}\\s+`, 'm'));
  return (next === -1 ? rest : rest.slice(0, next)).trim();
}

function extractLabeledValue(content, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  const match = new RegExp(`^-\\s*\\*\\*${escaped}\\*\\*:\\s*(.+?)\\s*$`, 'im').exec(content);
  return match ? normalizeCell(match[1]) : '';
}

function validateDesignStructure(content, scenarioPairs) {
  const issues = [];
  if (content.trim().length < 50) {
    issues.push({ level: 'ERROR', path: 'design.md', message: 'design.md is too short (< 50 chars) — provide decisions, coverage, trade-offs, and affected areas' });
  }

  const coverageSection = extractSection(content, 'Requirement And Scenario Coverage');
  if (!coverageSection) {
    issues.push({ level: 'ERROR', path: 'design.md', message: 'Missing ## Requirement And Scenario Coverage' });
    return { ...makeReport(issues), coverageRows: new Map() };
  }

  const table = parseMarkdownTable(coverageSection, ['requirement', 'scenario', 'design decision', 'affected area', 'why here'], 'Design coverage');
  if (table.error) {
    issues.push({ level: 'ERROR', path: 'design.md', message: table.error });
    return { ...makeReport(issues), coverageRows: new Map() };
  }

  const coverageRows = new Map();
  for (const row of table.rows) {
    const key = coverageKey(row.requirement, row.scenario);
    for (const field of ['requirement', 'scenario']) {
      if (!isMeaningfulCell(row[field])) {
        issues.push({ level: 'ERROR', path: 'design.md', message: `Design coverage row requires ${field}` });
      }
    }
    if (coverageRows.has(key)) {
      issues.push({ level: 'ERROR', path: 'design.md', message: `Duplicate design coverage row: ${row.requirement} / ${row.scenario}` });
      continue;
    }
    coverageRows.set(key, row);
    for (const field of ['design decision', 'affected area', 'why here']) {
      if (!isMeaningfulCell(row[field])) {
        issues.push({ level: 'ERROR', path: 'design.md', message: `Design coverage for "${row.requirement} / ${row.scenario}" requires ${field}` });
      }
    }
  }

  const decisionsSection = extractSection(content, 'Decisions') || extractSection(content, '决策') || '';
  const decisionNames = new Set();
  const decisionRegex = /^###\s+(?:Decision:\s*)?(.+?)\s*$/gim;
  let decisionMatch;
  while ((decisionMatch = decisionRegex.exec(decisionsSection)) !== null) {
    decisionNames.add(normalizeRequirementName(decisionMatch[1]));
  }

  for (const pair of scenarioPairs) {
    const row = coverageRows.get(coverageKey(pair.requirement, pair.scenario));
    if (!row) {
      issues.push({ level: 'ERROR', path: 'design.md', message: `Scenario missing from design coverage: ${pair.requirement} / ${pair.scenario}` });
      continue;
    }
    const decision = normalizeDecisionName(row['design decision']);
    if (decision !== 'no design change' && !decisionNames.has(decision)) {
      issues.push({ level: 'ERROR', path: 'design.md', message: `Design coverage references missing decision: ${row['design decision']}` });
    }
  }

  const expectedKeys = new Set(scenarioPairs.map(pair => coverageKey(pair.requirement, pair.scenario)));
  for (const row of coverageRows.values()) {
    if (!expectedKeys.has(coverageKey(row.requirement, row.scenario))) {
      issues.push({ level: 'WARNING', path: 'design.md', message: `Design coverage row has no matching spec Scenario: ${row.requirement} / ${row.scenario}` });
    }
  }

  return { ...makeReport(issues), coverageRows };
}

function extractTaskBatches(content) {
  const headings = [];
  const regex = /^##\s+(?:\d+\.\s*)?(Batch\s+\d+)\b[^\n]*$/gim;
  let match;
  while ((match = regex.exec(content)) !== null) headings.push({ name: match[1], start: match.index, bodyStart: regex.lastIndex });
  return headings.map((heading, index) => ({
    name: heading.name,
    content: content.slice(heading.bodyStart, headings[index + 1]?.start ?? content.length),
  }));
}

function extractTaskAcs(content) {
  const headings = [];
  const regex = /^###\s+AC:\s*(.+?)\s*$/gim;
  let match;
  while ((match = regex.exec(content)) !== null) {
    headings.push({ scenario: normalizeCell(match[1]), start: match.index, bodyStart: regex.lastIndex });
  }
  return headings.map((heading, index) => ({
    scenario: heading.scenario,
    content: content.slice(heading.bodyStart, headings[index + 1]?.start ?? content.length),
  }));
}

function validateFileChanges(scopeName, content, headingLevel = 5) {
  const issues = [];
  const hashes = '#'.repeat(headingLevel);
  const fileRegex = new RegExp('^' + hashes + '\\s+(Create|Modify|Delete)\\s+`([^`]+)`\\s*$', 'gim');
  const files = [];
  let match;
  while ((match = fileRegex.exec(content)) !== null) files.push({ action: match[1], path: match[2], bodyStart: fileRegex.lastIndex, headingStart: match.index });
  if (files.length === 0) {
    issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} File Changes must contain at least one ${hashes} Create/Modify/Delete \`path\` heading` });
    return issues;
  }
  files.forEach((file, index) => {
    const body = content.slice(file.bodyStart, files[index + 1]?.headingStart ?? content.length);
    if (!/\*\*(?:Change|Add|Responsibility)\*\*:\s*\S+/i.test(body)) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} file ${file.path} needs a concrete Change, Add, or Responsibility explanation` });
    }
  });
  return issues;
}

function validateTasksStructure(content, scenarioPairs, designCoverageRows, designExists, projectRoot) {
  const issues = [];
  const testRows = [];
  const exactTestCaseOwners = new Map();
  if (content.trim().length < 50) {
    issues.push({ level: 'ERROR', path: 'tasks.md', message: 'tasks.md is too short (< 50 chars) — provide covered scenarios, concrete file changes, and ordered TDD steps' });
  }

  const batches = extractTaskBatches(content);
  if (batches.length === 0) issues.push({ level: 'ERROR', path: 'tasks.md', message: 'tasks.md must contain at least one ## Batch N heading' });
  const covered = new Map();
  const expectedKeys = new Set(scenarioPairs.map(pair => coverageKey(pair.requirement, pair.scenario)));

  for (const batch of batches) {
    const acs = extractTaskAcs(batch.content);
    if (acs.length === 0) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `${batch.name} must contain at least one ### AC: <Scenario title> section` });
      continue;
    }

    for (const ac of acs) {
      const requirement = extractLabeledValue(ac.content, 'Requirement');
      const userVisible = normalizeRequirementName(extractLabeledValue(ac.content, 'User-visible'));
      const scopeName = `${batch.name} AC "${ac.scenario}"`;
      if (!isMeaningfulCell(requirement)) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} requires - **Requirement**: <exact Requirement title>` });
        continue;
      }

      const key = coverageKey(requirement, ac.scenario);
      if (covered.has(key)) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `Scenario assigned to multiple Batch AC sections: ${requirement} / ${ac.scenario}` });
      } else {
        covered.set(key, { requirement, scenario: ac.scenario, batch: batch.name });
      }

      if (!expectedKeys.has(key)) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `Task AC has no matching spec Scenario: ${requirement} / ${ac.scenario}` });
      }
      if (designExists && !designCoverageRows.has(key)) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `Task AC has no matching design.md coverage row: ${requirement} / ${ac.scenario}` });
      }
      if (!['yes', 'no'].includes(userVisible)) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} requires - **User-visible**: Yes or No` });
      }

      const fileChanges = extractNestedSection(ac.content, 'File Changes', 4);
      if (!fileChanges) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} is missing #### File Changes` });
      } else {
        issues.push(...validateFileChanges(scopeName, fileChanges));
      }

      const testPlan = extractNestedSection(ac.content, 'TDD Test Plan', 4);
      if (!testPlan) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} is missing #### TDD Test Plan` });
      } else {
        const table = parseMarkdownTable(testPlan, ['layer', 'platform', 'action', 'test file', 'test case', 'prove'], 'TDD Test Plan');
        if (table.error) {
          issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} ${table.error}` });
        } else if (table.rows.length === 0) {
          issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} TDD Test Plan requires at least one test row` });
        } else {
          const allowedLayers = new Set(['unit', 'component', 'integration', 'ui']);
          const allowedActions = new Set(['add', 'update', 'run existing', 'unavailable']);
          table.rows.forEach((row, index) => {
            const rowName = `${scopeName} TDD Test Plan row ${index + 1}`;
            if (!allowedLayers.has(normalizeRequirementName(row.layer))) {
              issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} Layer must be Unit, Component, Integration, or UI` });
            }
            if (!allowedActions.has(normalizeRequirementName(row.action))) {
              issues.push({ level: 'ERROR', path: 'tasks.md', message: `${rowName} Action must be Add, Update, Run existing, or Unavailable` });
            }
            issues.push(...validateTestPlanRow(rowName, row, projectRoot));
            const action = normalizeRequirementName(row.action);
            const testFile = normalizeCell(row['test file']);
            const testCase = normalizeCell(row['test case']);
            if (
              action !== 'unavailable'
              && isTestSourcePath(testFile)
              && isConcreteTestCase(testCase)
            ) {
              const ownershipKey = exactTestCaseOwnershipKey(row);
              const ownerKey = coverageKey(requirement, ac.scenario);
              const previousOwner = exactTestCaseOwners.get(ownershipKey);
              if (previousOwner && previousOwner.ownerKey !== ownerKey) {
                issues.push({
                  level: 'ERROR',
                  path: 'tasks.md',
                  message: `Exact Test Case has multiple AC owners: ${normalizeCell(row['test file']).replace(/\\/g, '/').toLowerCase()} / ${normalizeRequirementName(row['test case'])}; owners: ${previousOwner.requirement} / ${previousOwner.scenario} and ${requirement} / ${ac.scenario}`,
                });
              } else if (!previousOwner) {
                exactTestCaseOwners.set(ownershipKey, {
                  ownerKey,
                  requirement,
                  scenario: ac.scenario,
                });
              }
            }
            testRows.push({
              requirement,
              ac: ac.scenario,
              userVisible,
              batch: batch.name,
              ...row,
            });
          });
          if (userVisible === 'yes' && !table.rows.some(row => normalizeRequirementName(row.layer) === 'ui')) {
            issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} is user-visible and requires an AC-specific UI test row` });
          }
        }
      }

      const tddSteps = extractNestedSection(ac.content, 'TDD Steps', 4);
      if (!tddSteps) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} is missing #### TDD Steps` });
      } else if (!/-\s*\[[ xX]\]\s+\S+/.test(tddSteps)) {
        issues.push({ level: 'ERROR', path: 'tasks.md', message: `${scopeName} TDD Steps must contain executable checklist items` });
      }
    }
  }

  for (const pair of scenarioPairs) {
    if (!covered.has(coverageKey(pair.requirement, pair.scenario))) {
      issues.push({ level: 'ERROR', path: 'tasks.md', message: `Scenario missing from task coverage: ${pair.requirement} / ${pair.scenario}` });
    }
  }

  return { ...makeReport(issues), testRows };
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

function validateFrontendVerification(sectionContent, taskTestRows) {
  const issues = [];
  const impact = normalizeRequirementName(extractLabeledValue(sectionContent, 'Frontend Impact'));
  const reason = extractLabeledValue(sectionContent, 'Reason');
  if (!['yes', 'no'].includes(impact)) {
    issues.push({ level: 'ERROR', path: 'execution-contract.md', message: 'Frontend Verification requires - **Frontend Impact**: Yes or No' });
    return issues;
  }
  if (!isMeaningfulCell(reason)) {
    issues.push({ level: 'ERROR', path: 'execution-contract.md', message: 'Frontend Verification requires a concrete Reason' });
  }
  if (impact === 'no') return issues;

  const table = parseMarkdownTable(
    sectionContent,
    ['check', 'obligation', 'scope', 'target environment', 'command or procedure', 'evidence required'],
    'Frontend Verification',
  );
  if (table.error) {
    issues.push({ level: 'ERROR', path: 'execution-contract.md', message: table.error });
    return issues;
  }

  const rowsByCheck = new Map(table.rows.map(row => [normalizeRequirementName(row.check), row]));
  const uiRow = rowsByCheck.get('ui test');
  const deviceRow = rowsByCheck.get('device test');
  if (!uiRow) issues.push({ level: 'ERROR', path: 'execution-contract.md', message: 'Frontend Verification requires a UI Test row' });
  if (!deviceRow) issues.push({ level: 'ERROR', path: 'execution-contract.md', message: 'Frontend Verification requires a Device Test row' });
  if (!taskTestRows.some(row => normalizeRequirementName(row.layer) === 'ui')) {
    issues.push({ level: 'ERROR', path: 'execution-contract.md', message: 'Frontend Impact: Yes requires at least one UI row in the AC Test Matrix' });
  }

  for (const [name, row] of [['UI Test', uiRow], ['Device Test', deviceRow]]) {
    if (!row) continue;
    for (const field of ['scope', 'target environment', 'command or procedure', 'evidence required']) {
      if (!isMeaningfulCell(row[field])) {
        issues.push({ level: 'ERROR', path: 'execution-contract.md', message: `${name} requires ${field}` });
      }
    }
  }

  if (uiRow && normalizeRequirementName(uiRow.obligation) !== 'required by ac test matrix') {
    issues.push({ level: 'ERROR', path: 'execution-contract.md', message: 'UI Test obligation must be Required by AC Test Matrix' });
  }
  if (deviceRow && normalizeRequirementName(deviceRow.obligation) !== 'required') {
    issues.push({ level: 'ERROR', path: 'execution-contract.md', message: 'Device Test obligation must be Required for frontend work' });
  }

  return issues;
}

function validateSpecsLayout(changeDir, specsDir, specFiles) {
  const mdFiles = findFiles(specsDir, /\.md$/);
  const issues = [];

  for (const mdFile of mdFiles) {
    if (basename(mdFile) !== 'spec.md') {
      issues.push({
        level: 'ERROR',
        path: relative(changeDir, mdFile),
        message: 'Capability markdown files must be named spec.md inside a capability directory, for example specs/rate-limit/spec.md',
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

function validateExecutionContract(contractContent, requirementNames, taskTestRows) {
  const requiredSections = [
    'Intent Lock',
    'Approved Behavior',
    'Requirement Traceability',
    'AC Test Matrix',
    'Design Constraints',
    'Task Batches',
    'Test Obligations',
    'Frontend Verification',
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

  const frontendVerification = extractSection(contractContent, 'Frontend Verification');
  if (frontendVerification) issues.push(...validateFrontendVerification(frontendVerification, taskTestRows));
  issues.push(...validateAcTestMatrix(contractContent, taskTestRows));

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
  const scenarioPairs = [];
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
      scenarioPairs.push(...extractRequirementScenarioPairs(content));
    }
  }

  let designCoverageRows = new Map();
  const designPath = join(changeDir, 'design.md');
  const designExists = existsSync(designPath);
  if (designExists) {
    const report = validateDesignStructure(readFileSync(designPath, 'utf-8'), scenarioPairs);
    designCoverageRows = report.coverageRows;
    printReport('design.md', report);
    if (!report.valid) hasErrors = true;
  }

  const projectRoot = findProjectRoot(changeDir);
  let taskTestRows = [];
  const tasksPath = join(changeDir, 'tasks.md');
  if (existsSync(tasksPath)) {
    const report = validateTasksStructure(readFileSync(tasksPath, 'utf-8'), scenarioPairs, designCoverageRows, designExists, projectRoot);
    taskTestRows = report.testRows;
    printReport('tasks.md', report);
    if (!report.valid) hasErrors = true;
  }

  const contractPath = join(changeDir, 'execution-contract.md');
  if (existsSync(contractPath)) {
    const content = readFileSync(contractPath, 'utf-8');
    const report = validateExecutionContract(content, requirementNames, taskTestRows);
    printReport('execution-contract.md', report);
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
