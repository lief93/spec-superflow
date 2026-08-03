import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';

import {
  computeReviewCandidate,
  REVIEW_STAGES,
} from '../../scripts/lib/review-candidate.mjs';

const PROPOSAL_IDENTITY = `sha256:${'1'.repeat(64)}`;
const DESIGN_IDENTITY = `sha256:${'2'.repeat(64)}`;

function createFixture() {
  const root = mkdtempSync(join(tmpdir(), 'ssf-review-candidate-'));
  git(root, ['init', '-q', '-b', 'main']);
  git(root, ['config', 'user.email', 'tests@example.com']);
  git(root, ['config', 'user.name', 'Spec Superflow Tests']);
  write(root, 'README.md', '# Baseline\n');
  write(root, 'src/tracked.mjs', 'export const value = 1;\n');
  git(root, ['add', '.']);
  git(root, ['commit', '-qm', 'baseline']);
  const base = git(root, ['rev-parse', 'HEAD']);
  const changeDir = join(root, 'changes', 'example');
  const files = {
    'user-intent.md': '# Intent\nKeep review independent.\n',
    'proposal.md': '# Proposal\nAdd three review stages.\n',
    'specs/alpha/spec.md': '# Alpha\nRequired behavior.\n',
    'specs/zeta/spec.md': '# Zeta\nRequired edge case.\n',
    'design.md': '# Design\nUse one fixed Reviewer.\n',
    'tasks.md': '# Tasks\n\n## Batch 1\n- [ ] **RED**: run tests\n- [ ] **GREEN**: implement\n',
    'execution-contract.md': '# Contract\nUse the approved design.\n',
    'pr-summary.md': '# PR Summary\nTests pass.\n',
    'known-risks.md': '# Known Risks\nRuntime remains pending.\n',
    'runtime-evidence.md': '# Runtime Evidence\nVS Code: PENDING.\n',
  };
  for (const [path, content] of Object.entries(files)) write(changeDir, path, content);
  mkdirSync(join(changeDir, 'reviews'), { recursive: true });
  return { root, changeDir, base };
}

describe('minimal review candidates', () => {
  it('supports exactly the three semantic stages without graph protocol', () => {
    const fixture = createFixture();
    try {
      assert.deepEqual(REVIEW_STAGES, ['proposal-specs', 'design-tasks', 'final']);
      const candidate = computeReviewCandidate({
        changeDir: fixture.changeDir,
        stage: 'proposal-specs',
      });
      assert.equal(candidate.stage, 'proposal-specs');
      assert.match(candidate.identity, /^sha256:[a-f0-9]{64}$/);
      assert.deepEqual(candidate.inputs, [
        'user-intent.md',
        'proposal.md',
        'specs/alpha/spec.md',
        'specs/zeta/spec.md',
      ]);
      assert.deepEqual(candidate.review_targets, [
        'proposal.md',
        'specs/alpha/spec.md',
        'specs/zeta/spec.md',
      ]);
      assert.deepEqual(candidate.allowed_finding_paths, candidate.review_targets);
      assert.equal(Object.hasOwn(candidate, 'diff'), false);
      assert.equal(Object.hasOwn(candidate, 'untracked_files'), false);
      assert.doesNotMatch(JSON.stringify(candidate), /Keep review independent|Add three review stages/);
      for (const removed of [
        'candidate_graph',
        'message_graph',
        'handoff_attestation',
        'result_contract',
      ]) {
        assert.equal(Object.hasOwn(candidate, removed), false, removed);
      }
    } finally {
      rmSync(fixture.root, { recursive: true, force: true });
    }
  });

  it('binds Proposal and Specs identity to intent and every current target', () => {
    const fixture = createFixture();
    try {
      const current = () => computeReviewCandidate({
        changeDir: fixture.changeDir,
        stage: 'proposal-specs',
      }).identity;
      const initial = current();
      for (const path of ['user-intent.md', 'proposal.md', 'specs/alpha/spec.md']) {
        const absolute = join(fixture.changeDir, path);
        const before = readFileSync(absolute, 'utf8');
        writeFileSync(absolute, `${before}\nDrift.\n`);
        assert.notEqual(current(), initial, path);
        writeFileSync(absolute, before);
      }
    } finally {
      rmSync(fixture.root, { recursive: true, force: true });
    }
  });

  it('normalizes only real Tasks checkboxes for Design and Tasks identity', () => {
    const fixture = createFixture();
    try {
      const current = () => computeReviewCandidate({
        changeDir: fixture.changeDir,
        stage: 'design-tasks',
        prerequisiteIdentities: {
          'proposal-specs': PROPOSAL_IDENTITY,
        },
      });
      const initial = current();
      assert.deepEqual(initial.inputs, ['design.md', 'tasks.md']);
      assert.deepEqual(initial.review_targets, ['design.md', 'tasks.md']);

      const tasks = join(fixture.changeDir, 'tasks.md');
      const before = readFileSync(tasks, 'utf8');
      writeFileSync(tasks, before.replace('- [ ] **RED**', '- [x] **RED**'));
      assert.equal(current().identity, initial.identity);

      writeFileSync(tasks, before.replace('run tests', 'run all tests'));
      assert.notEqual(current().identity, initial.identity);

      writeFileSync(tasks, `${before}\n\`\`\`md\n- [ ] example\n\`\`\`\n`);
      const fenced = current().identity;
      writeFileSync(tasks, `${before}\n\`\`\`md\n- [x] example\n\`\`\`\n`);
      assert.notEqual(current().identity, fenced, 'fenced examples are semantic text');
    } finally {
      rmSync(fixture.root, { recursive: true, force: true });
    }
  });

  it('binds final identity to an explicit base, frozen evidence, and full Git state', () => {
    const fixture = createFixture();
    try {
      assert.throws(
        () => computeReviewCandidate({
          changeDir: fixture.changeDir,
          stage: 'final',
          prerequisiteIdentities: {
            'proposal-specs': PROPOSAL_IDENTITY,
            'design-tasks': DESIGN_IDENTITY,
          },
        }),
        /review base/i,
      );
      const current = () => computeReviewCandidate({
        changeDir: fixture.changeDir,
        stage: 'final',
        repoRoot: fixture.root,
        base: fixture.base,
        prerequisiteIdentities: {
          'proposal-specs': PROPOSAL_IDENTITY,
          'design-tasks': DESIGN_IDENTITY,
        },
      });
      const initial = current();
      assert.equal(initial.review_base, fixture.base);
      assert.deepEqual(initial.inputs, [
        'user-intent.md',
        'execution-contract.md',
        'pr-summary.md',
        'known-risks.md',
        'runtime-evidence.md',
      ]);

      write(fixture.root, 'src/untracked.mjs', 'export const untracked = true;\n');
      assert.notEqual(current().identity, initial.identity, 'untracked');
      rmSync(join(fixture.root, 'src/untracked.mjs'));

      write(fixture.root, 'src/staged.mjs', 'export const staged = true;\n');
      git(fixture.root, ['add', 'src/staged.mjs']);
      assert.notEqual(current().identity, initial.identity, 'staged');
      git(fixture.root, ['reset', '-q', 'HEAD', '--', 'src/staged.mjs']);
      rmSync(join(fixture.root, 'src/staged.mjs'));

      write(fixture.root, 'src/tracked.mjs', 'export const value = 2;\n');
      assert.notEqual(current().identity, initial.identity, 'unstaged');
      write(fixture.root, 'src/tracked.mjs', 'export const value = 1;\n');

      write(fixture.root, 'src/committed.mjs', 'export const committed = true;\n');
      git(fixture.root, ['add', 'src/committed.mjs']);
      git(fixture.root, ['commit', '-qm', 'candidate commit']);
      assert.notEqual(current().identity, initial.identity, 'committed');

      const evidence = join(fixture.changeDir, 'runtime-evidence.md');
      writeFileSync(evidence, '# Runtime Evidence\nVS Code: PASS.\n');
      assert.notEqual(current().identity, initial.identity, 'runtime evidence');
    } finally {
      rmSync(fixture.root, { recursive: true, force: true });
    }
  });

  it('keeps final candidate body-free while full tracked and untracked bytes bind identity', () => {
    const fixture = createFixture();
    try {
      const trackedSentinel = 'FINAL_TRACKED_SENTINEL_MUST_NOT_ENTER_JSON';
      const untrackedSentinel = 'FINAL_UNTRACKED_SENTINEL_MUST_NOT_ENTER_JSON';
      const firstTracked = `${trackedSentinel}\n${'a'.repeat(128 * 1024)}\n`;
      const firstUntracked = `${untrackedSentinel}\n${'b'.repeat(128 * 1024)}\n`;
      write(fixture.root, 'src/tracked.mjs', firstTracked);
      write(fixture.root, 'src/large-untracked.txt', firstUntracked);

      const current = () => computeReviewCandidate({
        changeDir: fixture.changeDir,
        stage: 'final',
        repoRoot: fixture.root,
        base: fixture.base,
        prerequisiteIdentities: {
          'proposal-specs': PROPOSAL_IDENTITY,
          'design-tasks': DESIGN_IDENTITY,
        },
      });
      const first = current();
      const trackedMetadata = first.changed_files.find(
        file => file.path === 'src/tracked.mjs',
      );
      const untrackedMetadata = first.changed_files.find(
        file => file.path === 'src/large-untracked.txt',
      );

      assert.equal(Object.hasOwn(first, 'diff'), false);
      assert.equal(Object.hasOwn(first, 'untracked_files'), false);
      assert.deepEqual(Object.keys(trackedMetadata).sort(), [
        'byte_length',
        'content_hash',
        'mode',
        'path',
        'status',
      ]);
      assert.deepEqual(Object.keys(untrackedMetadata).sort(), [
        'byte_length',
        'content_hash',
        'mode',
        'path',
        'status',
      ]);
      assert.equal(trackedMetadata.byte_length, Buffer.byteLength(firstTracked));
      assert.equal(untrackedMetadata.byte_length, Buffer.byteLength(firstUntracked));
      assert.match(trackedMetadata.content_hash, /^sha256:[a-f0-9]{64}$/);
      assert.match(untrackedMetadata.content_hash, /^sha256:[a-f0-9]{64}$/);
      const firstJson = JSON.stringify(first);
      assert.doesNotMatch(firstJson, new RegExp(trackedSentinel));
      assert.doesNotMatch(firstJson, new RegExp(untrackedSentinel));

      const secondTracked = `${'x'.repeat(trackedSentinel.length)}\n${'c'.repeat(128 * 1024)}\n`;
      const secondUntracked = `${'y'.repeat(untrackedSentinel.length)}\n${'d'.repeat(128 * 1024)}\n`;
      assert.equal(Buffer.byteLength(secondTracked), Buffer.byteLength(firstTracked));
      assert.equal(Buffer.byteLength(secondUntracked), Buffer.byteLength(firstUntracked));

      write(fixture.root, 'src/tracked.mjs', secondTracked);
      const trackedChanged = current();
      assert.notEqual(trackedChanged.identity, first.identity);
      assert.ok(Math.abs(JSON.stringify(trackedChanged).length - firstJson.length) <= 8);

      write(fixture.root, 'src/tracked.mjs', firstTracked);
      write(fixture.root, 'src/large-untracked.txt', secondUntracked);
      const untrackedChanged = current();
      assert.notEqual(untrackedChanged.identity, first.identity);
      assert.ok(Math.abs(JSON.stringify(untrackedChanged).length - firstJson.length) <= 8);
    } finally {
      rmSync(fixture.root, { recursive: true, force: true });
    }
  });

  it('frames the exact current upstream candidate identities into dependent stages', () => {
    const fixture = createFixture();
    try {
      const design = proposalIdentity => computeReviewCandidate({
        changeDir: fixture.changeDir,
        stage: 'design-tasks',
        prerequisiteIdentities: {
          'proposal-specs': proposalIdentity,
        },
      });
      const designV1 = design(PROPOSAL_IDENTITY);
      assert.notEqual(
        design(`sha256:${'3'.repeat(64)}`).identity,
        designV1.identity,
      );

      const final = prerequisiteIdentities => computeReviewCandidate({
        changeDir: fixture.changeDir,
        stage: 'final',
        repoRoot: fixture.root,
        base: fixture.base,
        prerequisiteIdentities,
      });
      const finalV1 = final({
        'proposal-specs': PROPOSAL_IDENTITY,
        'design-tasks': DESIGN_IDENTITY,
      });
      assert.notEqual(final({
        'proposal-specs': `sha256:${'4'.repeat(64)}`,
        'design-tasks': DESIGN_IDENTITY,
      }).identity, finalV1.identity, 'Proposal/Specs identity');
      assert.notEqual(final({
        'proposal-specs': PROPOSAL_IDENTITY,
        'design-tasks': `sha256:${'5'.repeat(64)}`,
      }).identity, finalV1.identity, 'Design/Tasks identity');
    } finally {
      rmSync(fixture.root, { recursive: true, force: true });
    }
  });
});

function write(root, relativePath, content) {
  const path = join(root, relativePath);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

function git(cwd, args) {
  const result = spawnSync('git', ['-C', cwd, ...args], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}
