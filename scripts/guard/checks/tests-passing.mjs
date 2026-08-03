// scripts/guard/checks/tests-passing.mjs — verify test_result is recorded as pass
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { readState } from '../../lib/state-loader.mjs';

function normalize(value = '') {
  return String(value ?? '').replace(/[`*_]/g, '').trim().toLowerCase();
}

function extractSection(content, title) {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp(`^##[ \\t]+${escaped}[ \\t]*$`, 'mi').exec(content);
  if (!match) return '';
  const bodyStart = match.index + match[0].length;
  const next = /^##[ \t]+.+$/m.exec(content.slice(bodyStart));
  return content.slice(bodyStart, next ? bodyStart + next.index : content.length);
}

function extractHeadingSection(content, title, level) {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const hashes = '#'.repeat(level);
  const match = new RegExp(`^${hashes}[ \\t]+${escaped}[ \\t]*$`, 'mi').exec(content);
  if (!match) return '';
  const bodyStart = match.index + match[0].length;
  const next = new RegExp(`^#{1,${level}}[ \\t]+.+$`, 'm').exec(content.slice(bodyStart));
  return content.slice(bodyStart, next ? bodyStart + next.index : content.length);
}

function labeledValue(section, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^- \\*\\*${escaped}\\*\\*:[ \\t]*(.+)$`, 'mi').exec(section)?.[1]?.trim() || '';
}

function tableRowList(section) {
  const lines = section.split('\n').map(line => line.trim()).filter(line => line.startsWith('|'));
  if (lines.length < 3) return [];
  const cells = line => line.slice(1, line.endsWith('|') ? -1 : undefined).split('|').map(cell => cell.trim());
  const headers = cells(lines[0]).map(normalize);
  return lines.slice(2).map(line => {
    const values = cells(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] || '']));
  });
}

function tableRows(section) {
  const rows = new Map();
  for (const row of tableRowList(section)) {
    if (row.check) rows.set(normalize(row.check), row);
  }
  return rows;
}

function meaningful(value) {
  const normalized = normalize(value);
  return normalized.length > 0 && !['-', '—', 'n/a', 'tbd', 'pending'].includes(normalized);
}

function acEvidenceKey(row) {
  return ['requirement', 'ac', 'layer', 'platform', 'test file', 'test case']
    .map(field => normalize(row[field]))
    .join('\u0000');
}

function plannedTestRows(changeDir, contractContent) {
  const tasksPath = join(changeDir, 'tasks.md');
  if (existsSync(tasksPath)) {
    const content = readFileSync(tasksPath, 'utf-8');
    const headings = [...content.matchAll(/^###\s+AC:\s*(.+?)\s*$/gim)];
    if (headings.length > 0) {
      const rows = [];
      headings.forEach((heading, index) => {
        const bodyStart = heading.index + heading[0].length;
        const body = content.slice(bodyStart, headings[index + 1]?.index ?? content.length);
        const requirement = labeledValue(body, 'Requirement');
        const plan = extractHeadingSection(body, 'TDD Test Plan', 4);
        for (const row of tableRowList(plan)) {
          rows.push({ requirement, ac: heading[1].trim(), ...row });
        }
      });
      return { configured: true, source: 'tasks.md TDD Test Plans', rows };
    }
  }

  const matrixSection = extractSection(contractContent, 'AC Test Matrix');
  if (!matrixSection) return { configured: false, source: '', rows: [] };
  return { configured: true, source: 'execution-contract.md AC Test Matrix', rows: tableRowList(matrixSection) };
}

function checkAcTestEvidence(changeDir, planned) {
  if (!planned.configured) return [];
  const plannedRows = planned.rows;
  if (plannedRows.length === 0) return [`${planned.source} has no test obligations.`];

  const summaryPath = join(changeDir, 'pr-summary.md');
  if (!existsSync(summaryPath)) return ['AC test evidence is missing: pr-summary.md does not exist.'];
  const evidenceSection = extractSection(readFileSync(summaryPath, 'utf-8'), 'AC Test Evidence');
  if (!evidenceSection) return ['pr-summary.md is missing ## AC Test Evidence.'];

  const failures = [];
  const evidenceRows = new Map();
  for (const row of tableRowList(evidenceSection)) {
    const key = acEvidenceKey(row);
    if (evidenceRows.has(key)) {
      failures.push(`AC Test Evidence contains a duplicate row: ${row.requirement} / ${row.ac} / ${row['test file']} / ${row['test case']}.`);
    }
    evidenceRows.set(key, row);
  }
  for (const planned of plannedRows) {
    const actual = evidenceRows.get(acEvidenceKey(planned));
    const label = `${planned.requirement || 'unknown requirement'} / ${planned.ac || 'unknown AC'} / ${planned['test file'] || 'unknown file'} / ${planned['test case'] || 'unknown case'}`;
    if (!actual) {
      failures.push(`AC Test Evidence is missing planned test: ${label}.`);
      continue;
    }
    const expectedResult = normalize(planned.action) === 'unavailable' ? 'unavailable' : 'pass';
    if (normalize(actual.result) !== expectedResult) {
      failures.push(`AC Test Evidence result for ${label} is '${actual.result || 'missing'}' — expected '${expectedResult === 'pass' ? 'Pass' : 'Unavailable'}'.`);
    }
    for (const field of ['command', 'evidence']) {
      if (!meaningful(actual[field])) failures.push(`AC Test Evidence for ${label} requires concrete ${field}.`);
    }
  }
  return failures;
}

function checkFrontendEvidence(changeDir, state) {
  const contractPath = join(changeDir, 'execution-contract.md');
  if (!existsSync(contractPath)) return [];

  const contractContent = readFileSync(contractPath, 'utf-8');
  const planned = plannedTestRows(changeDir, contractContent);
  const failures = checkAcTestEvidence(changeDir, planned);
  const uiRows = planned.rows.filter(row => normalize(row.layer) === 'ui');
  const hasUnavailableUi = uiRows.some(row => normalize(row.action) === 'unavailable');
  const contractSection = extractSection(contractContent, 'Frontend Verification');
  if (!contractSection || normalize(labeledValue(contractSection, 'Frontend Impact')) !== 'yes') return failures;

  const summaryPath = join(changeDir, 'pr-summary.md');
  if (!existsSync(summaryPath)) return [...failures, 'Frontend verification evidence is missing: pr-summary.md does not exist.'];
  const summarySection = extractSection(readFileSync(summaryPath, 'utf-8'), 'Frontend Verification Evidence');
  if (!summarySection) return [...failures, 'pr-summary.md is missing ## Frontend Verification Evidence.'];
  if (normalize(labeledValue(summarySection, 'Frontend Impact')) !== 'yes') {
    return [...failures, 'pr-summary.md must record Frontend Impact: Yes to match execution-contract.md.'];
  }

  const plannedRows = tableRows(contractSection);
  const actualRows = tableRows(summarySection);
  for (const check of ['ui test', 'device test']) {
    const planned = plannedRows.get(check);
    const actual = actualRows.get(check);
    const label = check === 'ui test' ? 'UI Test' : 'Device Test';
    if (!planned || !actual) {
      failures.push(`${label} planning or evidence row is missing.`);
      continue;
    }
    if (normalize(actual['planned obligation']) !== normalize(planned.obligation)) {
      failures.push(`${label} planned obligation does not match execution-contract.md.`);
    }
    const expectedResult = check === 'ui test' && hasUnavailableUi ? 'unavailable' : 'pass';
    if (normalize(actual.result) !== expectedResult) {
      failures.push(`${label} result is '${actual.result || 'missing'}' — expected '${expectedResult === 'pass' ? 'Pass' : 'Unavailable'}'.`);
    }
    for (const field of ['environment', 'command or procedure', 'evidence']) {
      if (!meaningful(actual[field])) failures.push(`${label} requires concrete ${field}.`);
    }
  }
  if (hasUnavailableUi) {
    if (!normalize(state.dp_6_result).startsWith('confirmed conditional:')) {
      failures.push('UI Test is Unavailable and requires a developer-confirmed conditional DP-6 decision.');
    }
  }
  return failures;
}

/**
 * Check that .spec-superflow.yaml records test_result: pass.
 * This field is set by release-archivist after verification.
 * Returns { pass, failures[] }.
 */
export function checkTestsPassing(changeDir) {
  const state = readState(changeDir);
  if (state.test_result !== 'pass') {
    return {
      pass: false,
      failures: [`test_result is '${state.test_result || 'null'}' — expected 'pass'. Run release-archivist verification first.`],
    };
  }
  const failures = checkFrontendEvidence(changeDir, state);
  return { pass: failures.length === 0, failures };
}
