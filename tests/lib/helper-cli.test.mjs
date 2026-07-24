import assert from 'node:assert/strict';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { after, before, describe, it } from 'node:test';

const CLI = join(process.cwd(), 'scripts', 'spec-superflow.mjs');
let tempDir;

function runSsf(args, cwd = tempDir) {
  return execFileSync(process.execPath, [CLI, ...args], {
    cwd,
    encoding: 'utf-8',
  });
}

function runGit(args, cwd) {
  return execFileSync('git', args, { cwd, encoding: 'utf-8' }).trim();
}

describe('ssf bundled helper commands', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-helper-cli-'));
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('exposes helper commands in CLI help', () => {
    const help = runSsf(['--help']);

    for (const command of [
      'check-update',
      'infer-workflow',
      'guard check',
      'task-brief',
      'review-package',
    ]) {
      assert.match(help, new RegExp(command.replace(' ', '\\s+')));
    }
  });

  it('runs workflow inference through ssf', () => {
    const changeDir = join(tempDir, 'changes', 'small-fix');
    mkdirSync(changeDir, { recursive: true });
    writeFileSync(join(changeDir, 'proposal.md'), 'Fix copy in README.md.\n');
    writeFileSync(join(changeDir, 'tasks.md'), '- [ ] Update README.md\n');

    const result = JSON.parse(runSsf(['infer-workflow', changeDir]));

    assert.equal(result.mode, 'hotfix');
  });

  it('runs transition guards through ssf', () => {
    const output = runSsf([
      'guard',
      'check',
      tempDir,
      'executing',
      'debugging',
      '--json',
    ]);

    assert.deepEqual(JSON.parse(output), { pass: true, checks: [] });
  });

  it('writes task briefs into the target repository by default', () => {
    const repo = join(tempDir, 'brief-repo');
    mkdirSync(repo, { recursive: true });
    runGit(['init', '-q'], repo);
    const plan = join(repo, 'tasks.md');
    writeFileSync(plan, '## Batch 1: UI\n### AC: Empty state\nShow the message.\n');

    runSsf(['task-brief', plan, '1'], repo);

    const brief = join(repo, '.superpowers', 'sdd', 'task-1-brief.md');
    assert.equal(existsSync(brief), true);
    assert.match(readFileSync(brief, 'utf-8'), /AC: Empty state/);
  });

  it('writes review packages into the target repository by default', () => {
    const repo = join(tempDir, 'review-repo');
    mkdirSync(repo, { recursive: true });
    runGit(['init', '-q'], repo);
    runGit(['config', 'user.name', 'CLI Test'], repo);
    runGit(['config', 'user.email', 'cli-test@example.invalid'], repo);
    writeFileSync(join(repo, 'sample.txt'), 'before\n');
    runGit(['add', 'sample.txt'], repo);
    runGit(['commit', '-qm', 'baseline'], repo);
    writeFileSync(join(repo, 'sample.txt'), 'after\n');
    runGit(['commit', '-qam', 'change'], repo);

    const base = runGit(['rev-parse', '--short', 'HEAD~1'], repo);
    const head = runGit(['rev-parse', '--short', 'HEAD'], repo);
    runSsf(['review-package', 'HEAD~1', 'HEAD'], repo);

    const review = join(
      repo,
      '.superpowers',
      'sdd',
      `review-${base}..${head}.diff`,
    );
    assert.equal(existsSync(review), true);
    assert.match(readFileSync(review, 'utf-8'), /after/);
  });
});
