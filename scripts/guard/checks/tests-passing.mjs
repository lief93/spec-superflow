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

function labeledValue(section, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^- \\*\\*${escaped}\\*\\*:[ \\t]*(.+)$`, 'mi').exec(section)?.[1]?.trim() || '';
}

function tableRows(section) {
  const lines = section.split('\n').map(line => line.trim()).filter(line => line.startsWith('|'));
  if (lines.length < 3) return new Map();
  const cells = line => line.slice(1, line.endsWith('|') ? -1 : undefined).split('|').map(cell => cell.trim());
  const headers = cells(lines[0]).map(normalize);
  const rows = new Map();
  for (const line of lines.slice(2)) {
    const values = cells(line);
    const row = Object.fromEntries(headers.map((header, index) => [header, values[index] || '']));
    if (row.check) rows.set(normalize(row.check), row);
  }
  return rows;
}

function meaningful(value) {
  const normalized = normalize(value);
  return normalized.length > 0 && !['-', '—', 'n/a', 'tbd', 'pending'].includes(normalized);
}

function checkFrontendEvidence(changeDir, state) {
  const contractPath = join(changeDir, 'execution-contract.md');
  if (!existsSync(contractPath)) return [];

  const contractSection = extractSection(readFileSync(contractPath, 'utf-8'), 'Frontend Verification');
  if (!contractSection || normalize(labeledValue(contractSection, 'Frontend Impact')) !== 'yes') return [];

  const summaryPath = join(changeDir, 'pr-summary.md');
  if (!existsSync(summaryPath)) return ['Frontend verification evidence is missing: pr-summary.md does not exist.'];
  const summarySection = extractSection(readFileSync(summaryPath, 'utf-8'), 'Frontend Verification Evidence');
  if (!summarySection) return ['pr-summary.md is missing ## Frontend Verification Evidence.'];
  if (normalize(labeledValue(summarySection, 'Frontend Impact')) !== 'yes') {
    return ['pr-summary.md must record Frontend Impact: Yes to match execution-contract.md.'];
  }

  const plannedRows = tableRows(contractSection);
  const actualRows = tableRows(summarySection);
  const failures = [];
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
    const expectedResult = check === 'ui test' && normalize(planned.obligation) === 'unavailable' ? 'unavailable' : 'pass';
    if (normalize(actual.result) !== expectedResult) {
      failures.push(`${label} result is '${actual.result || 'missing'}' — expected '${expectedResult === 'pass' ? 'Pass' : 'Unavailable'}'.`);
    }
    for (const field of ['environment', 'command or procedure', 'evidence']) {
      if (!meaningful(actual[field])) failures.push(`${label} requires concrete ${field}.`);
    }
  }
  if (normalize(plannedRows.get('ui test')?.obligation) === 'unavailable') {
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
