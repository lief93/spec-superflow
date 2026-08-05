#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const EXPECTED_CANARIES = new Map([
  ['ask-matt', 'explicit'],
  ['diagnosing-bugs', 'automatic'],
]);
const EXPECTED_PENDING = [
  'grill-with-docs',
  'triage',
  'improve-codebase-architecture',
  'setup-matt-pocock-skills',
  'tdd',
  'to-spec',
  'to-tickets',
  'wayfinder',
  'implement',
  'prototype',
  'research',
  'domain-modeling',
  'codebase-design',
  'code-review',
  'resolving-merge-conflicts',
  'grill-me',
  'grilling',
  'handoff',
  'teach',
  'writing-great-skills',
].sort();

function requireValue(value, label) {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`Missing ${label}.`);
  return value;
}

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function assertForbiddenActivity(value, skill) {
  if (!value || value.ssf !== false || value.workflowInit !== false || value.specChanges !== false) {
    throw new Error(`${skill} must record all forbidden activity as false.`);
  }
}

export function validateMattVscodeEvidence(evidence, { allowSynthetic = false } = {}) {
  if (!evidence || evidence.schemaVersion !== 1 || evidence.evidenceKind !== 'vscode-runtime') {
    throw new Error('Unsupported evidence schema.');
  }
  if (evidence.synthetic && !allowSynthetic) throw new Error('Synthetic evidence cannot prove runtime PASS.');
  requireValue(evidence.capturedAt, 'capture timestamp');
  if (evidence.host?.name !== 'Visual Studio Code' || evidence.host?.version !== '1.123.0') {
    throw new Error('Evidence must identify Visual Studio Code 1.123.0.');
  }

  const pkg = evidence.package || {};
  if (pkg.extensionId !== 'magebyte.spec-superflow-companion') throw new Error('Wrong package identity.');
  requireValue(pkg.vsixPath, 'VSIX path');
  if (!/^[0-9a-f]{64}$/i.test(pkg.sha256 || '')) throw new Error('Missing or invalid VSIX SHA-256.');
  if (JSON.stringify(pkg.pluginRoots) !== JSON.stringify(['agent-plugin', 'matt-plugin'])) {
    throw new Error('Wrong Plugin roots.');
  }
  if (pkg.mattCommit !== '2ab958093e83e0ec752e6c1c5932da465bf23e0c') {
    throw new Error('Wrong Matt source commit.');
  }
  if (!evidence.synthetic) {
    if (!existsSync(pkg.vsixPath)) throw new Error('Bound VSIX does not exist.');
    if (sha256(pkg.vsixPath) !== pkg.sha256) throw new Error('Bound VSIX digest does not match.');
  }

  if (JSON.stringify(evidence.network?.allowed) !== JSON.stringify(['configured Copilot model service'])) {
    throw new Error('Allowed network boundary is not exact.');
  }
  for (const denied of ['upstream Git', 'package registry', 'optional MCP', 'Plugin content fetch']) {
    if (!evidence.network?.blocked?.includes(denied)) throw new Error(`Missing blocked network boundary: ${denied}`);
  }

  if (!Array.isArray(evidence.canaries) || evidence.canaries.length !== 2) {
    throw new Error('Exactly two per-Skill canaries are required.');
  }
  const seen = new Set();
  for (const canary of evidence.canaries) {
    const invocation = EXPECTED_CANARIES.get(canary.skill);
    if (!invocation) throw new Error(`Skill is not approved as a canary: ${canary.skill}`);
    if (seen.has(canary.skill)) throw new Error(`Duplicate canary: ${canary.skill}`);
    seen.add(canary.skill);
    if (canary.agent !== 'Matt Engineering' || canary.invocation !== invocation || canary.result !== 'PASS') {
      throw new Error(`Invalid ${canary.skill} Agent, invocation, or result.`);
    }
    requireValue(canary.prompt, `${canary.skill} prompt`);
    requireValue(canary.response, `${canary.skill} response`);
    requireValue(canary.tracePath, `${canary.skill} trace path`);
    assertForbiddenActivity(canary.forbiddenActivity, canary.skill);
  }

  if (evidence.specSmoke?.agent !== 'Spec Superflow' || evidence.specSmoke?.result !== 'PASS') {
    throw new Error('Independent Spec Superflow smoke evidence is required.');
  }
  requireValue(evidence.specSmoke.tracePath, 'Spec smoke trace path');
  const pending = [...(evidence.pendingSkills || [])].sort();
  if (JSON.stringify(pending) !== JSON.stringify(EXPECTED_PENDING)) {
    throw new Error('Every unexecuted Skill must remain PENDING.');
  }
  if (evidence.duplicateNameResolution?.name !== 'grill-me'
    || evidence.duplicateNameResolution?.status !== 'PENDING') {
    throw new Error('Duplicate grill-me resolution must remain PENDING.');
  }
  const restoration = evidence.restoration || {};
  if (restoration.result !== 'PASS' || restoration.before !== restoration.after
    || restoration.candidateProcesses !== 0 || restoration.candidateConfigReferences !== 0) {
    throw new Error('Environment restoration evidence is incomplete.');
  }
  if (!Array.isArray(evidence.secretScan?.exposedValues)
    || evidence.secretScan.exposedValues.length !== 0) {
    throw new Error('Evidence contains or reports an exposed secret.');
  }
  const visibleText = JSON.stringify(evidence.canaries);
  if (/\bBearer\s+[A-Za-z0-9._-]+|\bsk-[A-Za-z0-9]{8,}|token-value/i.test(visibleText)) {
    throw new Error('Canary evidence appears to expose a secret.');
  }

  return { canaries: 2, pendingSkills: 20, synthetic: Boolean(evidence.synthetic) };
}

const invoked = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invoked) {
  const input = process.argv[2];
  if (!input) throw new Error('Usage: node scripts/check-matt-vscode-evidence.mjs <evidence.json>');
  const result = validateMattVscodeEvidence(JSON.parse(readFileSync(resolve(input), 'utf8')));
  process.stdout.write(`${JSON.stringify({ status: 'PASS', ...result })}\n`);
}
