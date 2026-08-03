import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { it } from 'node:test';

import {
  computeReviewCandidate,
} from '../../scripts/lib/review-candidate.mjs';
import {
  collectWorktreeReviewCandidate,
} from '../../scripts/lib/worktree-review-candidate.mjs';

it('collects committed staged unstaged and untracked candidate state without an artifact', () => {
  const fixture = createRepo();
  try {
    const candidate = collectWorktreeReviewCandidate({
      repoRoot: fixture.repo,
      changeDir: fixture.changeDir,
      base: fixture.base,
    });
    const paths = new Set(candidate.changedFiles.map(file => file.path));

    for (const path of [
      'src/committed.mjs',
      'src/staged.mjs',
      'README.md',
      'src/deleted.mjs',
      'src/renamed-to.mjs',
      'src/tracked.bin',
      'src/untracked.txt',
      'src/untracked.bin',
    ]) {
      assert.equal(paths.has(path), true, path);
    }
    assert.match(candidate.identity, /^sha256:[a-f0-9]{64}$/);
    assert.match(candidate.diff, /src\/committed\.mjs/);
    assert.match(candidate.diff, /src\/staged\.mjs/);
    assert.match(candidate.diff, /README\.md/);
    assert.match(candidate.diff, /GIT binary patch|Binary files differ/);
    assert.equal(
      candidate.untrackedFiles.find(file => file.path === 'src/untracked.txt')?.text,
      'untracked text content\n',
    );
    assert.equal(
      existsSync(join(fixture.changeDir, 'reviews', 'final-candidate.md')),
      false,
    );
  } finally {
    rmSync(fixture.repo, { recursive: true, force: true });
  }
});

it('final identity fails closed on semantic Git base and worktree drift', () => {
  const fixture = createRepo();
  try {
    const current = () => computeReviewCandidate({
      changeDir: fixture.changeDir,
      stage: 'final',
      repoRoot: fixture.repo,
      base: fixture.base,
      prerequisiteIdentities: {
        'proposal-specs': `sha256:${'1'.repeat(64)}`,
        'design-tasks': `sha256:${'2'.repeat(64)}`,
      },
    });
    const initial = current();

    git(fixture.repo, ['add', 'README.md']);
    assert.notEqual(
      current().identity,
      initial.identity,
      'moving the same tracked bytes from unstaged to staged must be stale',
    );
    git(fixture.repo, ['reset', '-q', 'HEAD', '--', 'README.md']);
    assert.equal(current().identity, initial.identity);

    write(
      fixture.repo,
      'README.md',
      '# Baseline\n\nUnstaged edit.\nLate tracked drift.\n',
    );
    assert.notEqual(current().identity, initial.identity);
    write(fixture.repo, 'README.md', '# Baseline\n\nUnstaged edit.\n');

    write(
      fixture.repo,
      'src/untracked.txt',
      'changed untracked content\n',
    );
    assert.notEqual(current().identity, initial.identity);
    write(fixture.repo, 'src/untracked.txt', 'untracked text content\n');

    write(
      fixture.repo,
      'changes/example/known-risks.md',
      '# Known Risks\n\n- Changed risk.\n',
    );
    assert.notEqual(current().identity, initial.identity);
    write(
      fixture.repo,
      'changes/example/known-risks.md',
      '# Known Risks\n\n- Runtime boundary remains.\n',
    );

    const laterBase = git(fixture.repo, ['rev-parse', 'HEAD']);
    const rebased = computeReviewCandidate({
      changeDir: fixture.changeDir,
      stage: 'final',
      repoRoot: fixture.repo,
      base: laterBase,
      prerequisiteIdentities: {
        'proposal-specs': `sha256:${'1'.repeat(64)}`,
        'design-tasks': `sha256:${'2'.repeat(64)}`,
      },
    });
    assert.notEqual(rebased.review_base, initial.review_base);
    assert.notEqual(rebased.identity, initial.identity);
  } finally {
    rmSync(fixture.repo, { recursive: true, force: true });
  }
});

it('collects changed gitlink metadata without reading the submodule directory as a file', () => {
  const fixture = createGitlinkRepo();
  try {
    const candidate = computeReviewCandidate({
      changeDir: fixture.changeDir,
      stage: 'final',
      repoRoot: fixture.repo,
      base: fixture.base,
      prerequisiteIdentities: {
        'proposal-specs': `sha256:${'1'.repeat(64)}`,
        'design-tasks': `sha256:${'2'.repeat(64)}`,
      },
    });
    const gitlink = candidate.changed_files.find(file => (
      file.path === 'vendor/dependency'
    ));

    assert.deepEqual(gitlink, {
      status: 'M',
      path: 'vendor/dependency',
      mode: '160000',
      byte_length: 40,
      content_hash: fixture.pointerHash,
    });
    assert.doesNotMatch(
      JSON.stringify(candidate),
      /GITLINK_SOURCE_BODY_SENTINEL/,
    );
  } finally {
    rmSync(fixture.repo, { recursive: true, force: true });
    rmSync(fixture.source, { recursive: true, force: true });
  }
});

it('binds gitlink pointer dirty and index-status changes into final identity', () => {
  const fixture = createGitlinkRepo();
  try {
    const current = () => computeReviewCandidate({
      changeDir: fixture.changeDir,
      stage: 'final',
      repoRoot: fixture.repo,
      base: fixture.base,
      prerequisiteIdentities: {
        'proposal-specs': `sha256:${'1'.repeat(64)}`,
        'design-tasks': `sha256:${'2'.repeat(64)}`,
      },
    });
    const pointerChanged = current();
    const pointerMetadata = pointerChanged.changed_files.find(file => (
      file.path === 'vendor/dependency'
    ));

    write(
      fixture.submodule,
      'dependency.mjs',
      `${fixture.pointerBody}// GITLINK_DIRTY_BODY_SENTINEL\n`,
    );
    const dirty = current();
    assert.notEqual(dirty.identity, pointerChanged.identity);
    assert.deepEqual(
      dirty.changed_files.find(file => file.path === 'vendor/dependency'),
      pointerMetadata,
    );
    assert.doesNotMatch(JSON.stringify(dirty), /GITLINK_DIRTY_BODY_SENTINEL/);

    write(fixture.submodule, 'dependency.mjs', fixture.pointerBody);
    assert.equal(current().identity, pointerChanged.identity);

    write(
      fixture.submodule,
      'dependency.mjs',
      'export const value = "GITLINK_NEXT_POINTER_BODY_SENTINEL";\n',
    );
    git(fixture.submodule, ['add', '.']);
    git(fixture.submodule, ['commit', '-qm', 'advance dependency again']);
    const nextPointer = current();
    const nextMetadata = nextPointer.changed_files.find(file => (
      file.path === 'vendor/dependency'
    ));
    assert.notEqual(nextPointer.identity, pointerChanged.identity);
    assert.notEqual(nextMetadata.content_hash, pointerMetadata.content_hash);
    assert.doesNotMatch(
      JSON.stringify(nextPointer),
      /GITLINK_NEXT_POINTER_BODY_SENTINEL/,
    );

    git(fixture.repo, ['add', 'vendor/dependency']);
    const staged = current();
    assert.notEqual(staged.identity, nextPointer.identity);
    assert.deepEqual(
      staged.changed_files.find(file => file.path === 'vendor/dependency'),
      nextMetadata,
    );
    git(fixture.repo, ['reset', '-q', 'HEAD', '--', 'vendor/dependency']);
    assert.equal(current().identity, nextPointer.identity);
  } finally {
    rmSync(fixture.repo, { recursive: true, force: true });
    rmSync(fixture.source, { recursive: true, force: true });
  }
});

function createRepo() {
  const repo = mkdtempSync(join(tmpdir(), 'ssf-worktree-candidate-'));
  git(repo, ['init', '-q', '-b', 'main']);
  git(repo, ['config', 'user.email', 'tests@example.com']);
  git(repo, ['config', 'user.name', 'Spec Superflow Tests']);

  write(repo, 'README.md', '# Baseline\n');
  write(repo, 'src/deleted.mjs', 'export const removed = true;\n');
  write(repo, 'src/renamed-from.mjs', 'export const renamed = true;\n');
  writeFileSync(join(repo, 'src', 'tracked.bin'), Buffer.from([0, 1, 2, 3]));
  git(repo, ['add', '.']);
  git(repo, ['commit', '-qm', 'baseline']);
  const base = git(repo, ['rev-parse', 'HEAD']);

  write(repo, 'src/committed.mjs', 'export const committed = true;\n');
  git(repo, ['add', 'src/committed.mjs']);
  git(repo, ['commit', '-qm', 'committed candidate']);

  write(repo, 'src/staged.mjs', 'export const staged = true;\n');
  git(repo, ['add', 'src/staged.mjs']);
  write(repo, 'README.md', '# Baseline\n\nUnstaged edit.\n');
  rmSync(join(repo, 'src', 'deleted.mjs'));
  git(repo, ['mv', 'src/renamed-from.mjs', 'src/renamed-to.mjs']);
  writeFileSync(join(repo, 'src', 'tracked.bin'), Buffer.from([0, 9, 2, 3]));
  write(repo, 'src/untracked.txt', 'untracked text content\n');
  writeFileSync(join(repo, 'src', 'untracked.bin'), Buffer.from([0, 255, 1, 254]));

  const changeDir = join(repo, 'changes', 'example');
  write(repo, 'changes/example/user-intent.md', '# Intent\nCurrent intent.\n');
  write(repo, 'changes/example/proposal.md', '# Proposal\nCurrent scope.\n');
  write(repo, 'changes/example/specs/example/spec.md', '# Spec\nCurrent behavior.\n');
  write(repo, 'changes/example/design.md', '# Design\nCurrent design.\n');
  write(repo, 'changes/example/tasks.md', '# Tasks\n- [x] Current task.\n');
  write(repo, 'changes/example/execution-contract.md', '# Contract\nCurrent contract.\n');
  write(repo, 'changes/example/pr-summary.md', '# PR Summary\n\n- npm test — PASS.\n');
  write(
    repo,
    'changes/example/known-risks.md',
    '# Known Risks\n\n- Runtime boundary remains.\n',
  );
  write(
    repo,
    'changes/example/runtime-evidence.md',
    '# Runtime Evidence\n\n- Persistence — UNSUPPORTED.\n',
  );
  mkdirSync(join(changeDir, 'reviews'), { recursive: true });
  return { repo, changeDir, base };
}

function createGitlinkRepo() {
  const source = mkdtempSync(join(tmpdir(), 'ssf-gitlink-source-'));
  git(source, ['init', '-q', '-b', 'main']);
  git(source, ['config', 'user.email', 'tests@example.com']);
  git(source, ['config', 'user.name', 'Spec Superflow Tests']);
  write(source, 'dependency.mjs', 'export const value = "baseline";\n');
  git(source, ['add', '.']);
  git(source, ['commit', '-qm', 'dependency baseline']);

  const repo = mkdtempSync(join(tmpdir(), 'ssf-gitlink-candidate-'));
  git(repo, ['init', '-q', '-b', 'main']);
  git(repo, ['config', 'user.email', 'tests@example.com']);
  git(repo, ['config', 'user.name', 'Spec Superflow Tests']);
  write(repo, 'README.md', '# Gitlink fixture\n');
  git(repo, [
    '-c',
    'protocol.file.allow=always',
    'submodule',
    'add',
    '-q',
    source,
    'vendor/dependency',
  ]);
  git(repo, ['add', '.']);
  git(repo, ['commit', '-qm', 'superproject baseline']);
  const base = git(repo, ['rev-parse', 'HEAD']);

  const submodule = join(repo, 'vendor', 'dependency');
  git(submodule, ['config', 'user.email', 'tests@example.com']);
  git(submodule, ['config', 'user.name', 'Spec Superflow Tests']);
  const pointerBody = 'export const value = "GITLINK_SOURCE_BODY_SENTINEL";\n';
  write(
    submodule,
    'dependency.mjs',
    pointerBody,
  );
  git(submodule, ['add', '.']);
  git(submodule, ['commit', '-qm', 'advance dependency pointer']);
  const pointer = git(submodule, ['rev-parse', 'HEAD']);
  const pointerHash = `sha256:${createHash('sha256').update(pointer).digest('hex')}`;

  const changeDir = join(repo, 'changes', 'example');
  write(repo, 'changes/example/user-intent.md', '# Intent\nCurrent intent.\n');
  write(repo, 'changes/example/execution-contract.md', '# Contract\nCurrent contract.\n');
  write(repo, 'changes/example/pr-summary.md', '# PR Summary\n\n- npm test — PASS.\n');
  write(repo, 'changes/example/known-risks.md', '# Known Risks\n\n- None.\n');
  write(repo, 'changes/example/runtime-evidence.md', '# Runtime Evidence\n\n- Local — PASS.\n');

  return {
    repo,
    source,
    submodule,
    changeDir,
    base,
    pointer,
    pointerBody,
    pointerHash,
  };
}

function write(root, relativePath, content) {
  const path = join(root, relativePath);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

function git(cwd, args) {
  const result = spawnSync('git', ['-C', cwd, ...args], {
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}
