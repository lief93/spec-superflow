import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';

const SCRIPT_PATH = join(process.cwd(), 'scripts/task-brief');
let tempDir;

function extract(plan, number) {
  const planPath = join(tempDir, `plan-${number}.md`);
  const outputPath = join(tempDir, `brief-${number}.md`);
  writeFileSync(planPath, plan);
  execFileSync(SCRIPT_PATH, [planPath, String(number), outputPath], { encoding: 'utf-8' });
  return readFileSync(outputPath, 'utf-8');
}

describe('task-brief', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-task-brief-'));
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('extracts a legacy numbered Task section', () => {
    const brief = extract(`# Plan
## Task 1: First
First body.
## Task 2: Second
Second body.
`, 2);

    assert.match(brief, /^## Task 2: Second/m);
    assert.match(brief, /Second body/);
    assert.doesNotMatch(brief, /First body/);
  });

  it('extracts an AC by order and includes its Batch context', () => {
    const brief = extract(`# Tasks
## Batch 1: Profile
### AC: Save a profile
First AC body.
### AC: Reject invalid names
Second AC body.
## Batch 2: Settings
### AC: Save settings
Third AC body.
`, 2);

    assert.match(brief, /^## Batch 1: Profile/m);
    assert.match(brief, /^### AC: Reject invalid names/m);
    assert.match(brief, /Second AC body/);
    assert.doesNotMatch(brief, /First AC body|Third AC body/);
  });

  it('ignores legacy-looking Task headings inside code fences', () => {
    const brief = extract(`# Tasks
\`\`\`markdown
## Task 1: Example only
\`\`\`
## Batch 1: Profile
### AC: Save a profile
Real AC body.
`, 1);

    assert.match(brief, /^### AC: Save a profile/m);
    assert.match(brief, /Real AC body/);
    assert.doesNotMatch(brief, /Example only/);
  });
});
