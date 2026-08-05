import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { validateMattVscodeEvidence } from '../../scripts/check-matt-vscode-evidence.mjs';

const SHA = 'a'.repeat(64);

function fixture() {
  return {
    schemaVersion: 1,
    evidenceKind: 'vscode-runtime',
    synthetic: true,
    capturedAt: '2026-08-05T00:00:00.000Z',
    host: { name: 'Visual Studio Code', version: '1.123.0' },
    package: {
      extensionId: 'magebyte.spec-superflow-companion',
      vsixPath: '/synthetic/spec-superflow.vsix',
      sha256: SHA,
      pluginRoots: ['agent-plugin', 'matt-plugin'],
      mattCommit: '2ab958093e83e0ec752e6c1c5932da465bf23e0c',
    },
    network: {
      allowed: ['configured Copilot model service'],
      blocked: ['upstream Git', 'package registry', 'optional MCP', 'Plugin content fetch'],
    },
    canaries: [
      {
        skill: 'ask-matt',
        agent: 'Matt Engineering',
        invocation: 'explicit',
        result: 'PASS',
        prompt: 'Use ask-matt to choose the right flow.',
        response: 'Ask Matt selected a suitable flow.',
        tracePath: '/synthetic/ask-matt.json',
        forbiddenActivity: { ssf: false, workflowInit: false, specChanges: false },
      },
      {
        skill: 'diagnosing-bugs',
        agent: 'Matt Engineering',
        invocation: 'automatic',
        result: 'PASS',
        prompt: 'Diagnose this intermittent failure.',
        response: 'First build a red-capable feedback loop.',
        tracePath: '/synthetic/diagnosing-bugs.json',
        forbiddenActivity: { ssf: false, workflowInit: false, specChanges: false },
      },
    ],
    specSmoke: { agent: 'Spec Superflow', result: 'PASS', tracePath: '/synthetic/spec.json' },
    pendingSkills: [
      'grill-with-docs', 'triage', 'improve-codebase-architecture',
      'setup-matt-pocock-skills', 'tdd', 'to-spec', 'to-tickets', 'wayfinder',
      'implement', 'prototype', 'research', 'domain-modeling', 'codebase-design',
      'code-review', 'resolving-merge-conflicts', 'grill-me', 'grilling', 'handoff',
      'teach', 'writing-great-skills',
    ],
    duplicateNameResolution: { name: 'grill-me', status: 'PENDING' },
    restoration: {
      result: 'PASS',
      before: 'isolated-profile-absent',
      after: 'isolated-profile-absent',
      candidateProcesses: 0,
      candidateConfigReferences: 0,
    },
    secretScan: { exposedValues: [] },
  };
}

describe('Matt VS Code runtime evidence gate', () => {
  it('accepts a complete synthetic schema only when explicitly enabled for tests', () => {
    assert.deepEqual(
      validateMattVscodeEvidence(fixture(), { allowSynthetic: true }),
      { canaries: 2, pendingSkills: 20, synthetic: true },
    );
    assert.throws(() => validateMattVscodeEvidence(fixture()), /synthetic/i);
  });

  it('rejects missing, aggregate, wrong-package, wrong-Agent, and leaked-secret evidence', () => {
    const cases = [];
    const missing = fixture();
    delete missing.package.sha256;
    cases.push(missing);
    const aggregate = fixture();
    aggregate.canaries = [{ result: 'PASS' }];
    cases.push(aggregate);
    const wrongPackage = fixture();
    wrongPackage.package.extensionId = 'other.extension';
    cases.push(wrongPackage);
    const wrongAgent = fixture();
    wrongAgent.canaries[0].agent = 'Spec Superflow';
    cases.push(wrongAgent);
    const leaked = fixture();
    leaked.secretScan.exposedValues = ['token-value'];
    cases.push(leaked);

    for (const evidence of cases) {
      assert.throws(() => validateMattVscodeEvidence(evidence, { allowSynthetic: true }));
    }
  });

  it('rejects incomplete canaries and false PASS claims for complex or duplicate Skills', () => {
    const incomplete = fixture();
    incomplete.canaries.pop();
    assert.throws(() => validateMattVscodeEvidence(incomplete, { allowSynthetic: true }), /canar/i);

    for (const skill of ['code-review', 'research', 'wayfinder', 'grill-me']) {
      const falsePass = fixture();
      falsePass.canaries.push({
        skill,
        agent: 'Matt Engineering',
        invocation: 'automatic',
        result: 'PASS',
        prompt: 'Synthetic',
        response: 'Synthetic',
        tracePath: '/synthetic/false-pass.json',
        forbiddenActivity: { ssf: false, workflowInit: false, specChanges: false },
      });
      assert.throws(() => validateMattVscodeEvidence(falsePass, { allowSynthetic: true }), /not approved|canar/i);
    }
  });
});
