import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');

function read(relativePath) {
  return readFileSync(join(root, relativePath), 'utf-8');
}

describe('project baseline workflow integration', () => {
  it('loads the baseline before task planning and preserves scenario traceability', () => {
    for (const skill of ['workflow-start', 'need-explorer', 'spec-writer', 'contract-builder']) {
      assert.match(read(`skills/${skill}/SKILL.md`), /docs\/project\/project-guidelines\.md/);
    }

    const design = read('templates/design.md');
    assert.match(design, /## Project Baseline Alignment/);
    assert.match(design, /\| Scenario \| Baseline Source \| Classic Implementation \|/);

    const contract = read('templates/execution-contract.md');
    assert.match(contract, /项目开发基线来源/);
    assert.match(contract, /采用的经典实现/);
    assert.match(contract, /已批准偏离/);
  });

  it('passes the selected baseline through implementation and independent review', () => {
    for (const skill of ['build-executor', 'code-reviewer', 'release-archivist']) {
      assert.match(
        read(`skills/${skill}/SKILL.md`),
        /project baseline|项目开发基线|docs\/project\/project-guidelines\.md/i,
      );
    }

    for (const prompt of [
      'skills/build-executor/implementer-prompt.md',
      'skills/build-executor/task-reviewer-prompt.md',
      'skills/code-reviewer/code-reviewer-prompt.md',
    ]) {
      const content = read(prompt);
      assert.match(content, /\[PROJECT_BASELINE\]/);
      assert.match(content, /classic implementation|经典实现/i);
    }
  });

  it('keeps project rules in the baseline instead of project memory', () => {
    const memory = read('skills/memory-manager/SKILL.md');
    assert.match(memory, /docs\/project\/project-guidelines\.md.*architecture\/coding rules/);
    assert.match(memory, /coding standards, architecture ownership, classic implementations/);
  });

  it('uses Claude-style selective recall throughout the workflow', () => {
    const workflowFiles = [
      'skills/workflow-start/SKILL.md',
      'skills/need-explorer/SKILL.md',
      'skills/spec-writer/SKILL.md',
      'skills/contract-builder/SKILL.md',
      'skills/build-executor/SKILL.md',
      'skills/bug-investigator/SKILL.md',
      'skills/code-reviewer/SKILL.md',
      'skills/release-archivist/SKILL.md',
    ];

    for (const file of workflowFiles) {
      assert.match(read(file), /MEMORY\.md|memory-manager/);
    }

    assert.match(read('skills/release-archivist/SKILL.md'), /Auto Memory Pass/);
    assert.doesNotMatch(workflowFiles.map(read).join('\n'), /memory_maintenance|`core`|core\.md|`mem:/);
  });

  it('keeps shared auto memory typed, indexed, and free of private user memory', () => {
    const memory = read('skills/memory-manager/SKILL.md');
    const entrypoint = read('skills/memory-manager/references/MEMORY.md');
    const topic = read('skills/memory-manager/references/TOPIC.md');

    assert.match(memory, /`feedback`.*`project`.*`reference`/s);
    assert.match(memory, /Private `user` memory and personal feedback are not supported/);
    assert.match(memory, /MEMORY\.md.*concise index/);
    assert.match(memory, /Candidate-First Evaluation/);
    assert.match(memory, /return `NONE` without a repository scan/);
    assert.equal(entrypoint, '# Project Memory\n');
    for (const field of ['name:', 'description:', 'type:', 'modified:']) {
      assert.match(topic, new RegExp(field));
    }
  });
});
