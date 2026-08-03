import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');
const read = path => readFileSync(join(root, path), 'utf-8');

const ownedTemplates = [
  ['spec-writer', 'proposal.md'],
  ['spec-writer', 'spec.md'],
  ['spec-writer', 'design.md'],
  ['spec-writer', 'tasks.md'],
  ['contract-builder', 'execution-contract.md'],
  ['release-archivist', 'pr-summary.md'],
  ['workflow-start', 'abandonment-summary.md'],
];

describe('skill-local artifact templates', () => {
  it('keeps one canonical template beside each artifact owner', () => {
    for (const [skill, template] of ownedTemplates) {
      const localPath = `skills/${skill}/references/${template}`;
      assert.equal(existsSync(join(root, localPath)), true, localPath);
      assert.equal(existsSync(join(root, 'templates', template)), false, `duplicate templates/${template}`);
      assert.match(read(`skills/${skill}/SKILL.md`), new RegExp(`references/${template.replace('.', '\\.')}`, 'i'), skill);
    }
  });

  it('preserves the externally validated artifact structures', () => {
    assert.match(read('skills/spec-writer/references/proposal.md'), /^## Why$/m);
    assert.match(read('skills/spec-writer/references/spec.md'), /^### Requirement:/m);
    assert.match(read('skills/spec-writer/references/design.md'), /^\| Requirement \| Scenario \| Design Decision \|/m);
    assert.match(read('skills/spec-writer/references/tasks.md'), /^#### TDD Test Plan$/m);
    assert.match(read('skills/contract-builder/references/execution-contract.md'), /^## Approved Artifacts$/m);
    assert.match(read('skills/release-archivist/references/pr-summary.md'), /^## AC Test Evidence$/m);
    assert.match(read('skills/workflow-start/references/abandonment-summary.md'), /^## Reason$/m);
  });
});
