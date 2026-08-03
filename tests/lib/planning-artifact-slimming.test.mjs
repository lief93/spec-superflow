import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');
const read = path => readFileSync(join(root, path), 'utf-8');

describe('planning artifact slimming', () => {
  it('keeps one design mapping table with baseline and reuse context', () => {
    const template = read('templates/design.md');
    const writer = read('skills/spec-writer/SKILL.md');

    assert.doesNotMatch(template, /^## Project Baseline Alignment$/m);
    assert.match(
      template,
      /^\| Requirement \| Scenario \| Design Decision \| Affected Area \| Baseline \/ Reuse \| Constraint \/ Deviation \| Why Here \|$/m,
    );
    assert.match(writer, /one coverage table/i);
    assert.doesNotMatch(writer, /every spec Scenario appears in both mapping tables/i);
  });

  it('moves repeated AC execution steps into one batch verification block', () => {
    const template = read('templates/tasks.md');
    const writer = read('skills/spec-writer/SKILL.md');

    assert.doesNotMatch(template, /^#### TDD Steps$/m);
    assert.match(template, /^### Batch Verification$/m);
    assert.match(writer, /one Batch Verification block per Batch/i);
    assert.match(writer, /observable signal/i);
    assert.match(writer, /no-op fake|no-op callback/i);
  });

  it('preserves the review chain from each AC to file rationale and exact tests', () => {
    const template = read('templates/tasks.md');
    const writer = read('skills/spec-writer/SKILL.md');
    const exactExample = /Use these exact Markdown headings[\s\S]*?```markdown([\s\S]*?)```/i.exec(writer)?.[1] || '';

    assert.match(template, /^### AC: \[Exact Scenario title from the Spec\]$/m);
    assert.match(template, /\*\*Why this file\*\*/);
    assert.match(template, /^#### TDD Test Plan$/m);
    assert.match(writer, /every AC.*at least one.*test row/i);
    assert.match(writer, /exact Requirement\/Scenario titles connect Spec, Design, and Tasks/i);
    assert.match(exactExample, /\*\*Why this file\*\*:/i);
  });

  it('uses state hashes instead of deleted contract scope prose for resume freshness', () => {
    const workflow = read('skills/workflow-start/SKILL.md');
    const stateMachine = read('docs/state-machine.md');

    assert.match(workflow, /ssf state check <change-dir>/i);
    assert.match(workflow, /artifacts_hash/i);
    assert.doesNotMatch(workflow, /contract scope fence/i);
    assert.match(stateMachine, /ssf state check/i);
    assert.doesNotMatch(stateMachine, /execution-contract\.md intent lock/i);
  });

  it('uses execution-contract as a compact lock instead of copying planning content', () => {
    const template = read('templates/execution-contract.md');
    const builder = read('skills/contract-builder/SKILL.md');

    for (const heading of ['Approved Artifacts', 'Execution Mode', 'Batch Gates', 'Verification', 'Frontend Verification', 'Stop Conditions']) {
      assert.match(template, new RegExp(`^## ${heading}$`, 'm'));
    }
    for (const duplicated of ['Approved Behavior', 'Requirement Traceability', 'AC Test Matrix', 'Design Constraints', 'Task Batches', 'Test Obligations', 'Verification Dimensions']) {
      assert.doesNotMatch(template, new RegExp(`^## ${duplicated}$`, 'm'));
    }
    assert.match(builder, /do not copy/i);
    assert.match(builder, /tasks\.md.*source of truth/i);
  });

  it('uses tasks test plans as the evidence source after implementation', () => {
    for (const path of [
      'templates/pr-summary.md',
      'skills/code-reviewer/SKILL.md',
      'skills/release-archivist/SKILL.md',
    ]) {
      const content = read(path);
      assert.match(content, /tasks\.md.*TDD Test Plan/i, path);
      assert.doesNotMatch(content, /execution-contract\.md > AC Test Matrix/i, path);
    }
  });
});
