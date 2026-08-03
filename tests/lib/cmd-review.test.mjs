import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const CLI = join(ROOT, 'scripts', 'spec-superflow.mjs');

function createFixture() {
  const repo = mkdtempSync(join(tmpdir(), 'ssf-cmd-review-'));
  git(repo, ['init', '-q', '-b', 'main']);
  git(repo, ['config', 'user.email', 'tests@example.com']);
  git(repo, ['config', 'user.name', 'Spec Superflow Tests']);
  write(repo, 'README.md', '# Baseline\n');
  git(repo, ['add', '.']);
  git(repo, ['commit', '-qm', 'baseline']);
  const base = git(repo, ['rev-parse', 'HEAD']);
  write(repo, 'src/feature.mjs', 'export const ready = true;\n');
  git(repo, ['add', 'src/feature.mjs']);
  git(repo, ['commit', '-qm', 'candidate']);
  const head = git(repo, ['rev-parse', 'HEAD']);

  const changeDir = join(repo, 'changes', 'example');
  const files = {
    'user-intent.md': '# Intent\nIndependent review.\n',
    'proposal.md': '# Proposal\nThree review stages.\n',
    'specs/example/spec.md': '# Spec\nRequired behavior.\n',
    'design.md': '# Design\nOne fixed Reviewer.\n',
    'tasks.md': '# Tasks\n\n## Batch 1\n- [ ] **RED**: run tests\n- [ ] **GREEN**: implement\n',
    'execution-contract.md': '# Contract\nApproved implementation.\n',
    'pr-summary.md': '# PR Summary\nTests pass.\n',
    'known-risks.md': '# Known Risks\nRuntime pending.\n',
    'runtime-evidence.md': '# Runtime Evidence\nVS Code: PENDING.\n',
  };
  for (const [path, content] of Object.entries(files)) write(changeDir, path, content);
  mkdirSync(join(changeDir, 'reviews'), { recursive: true });
  const initialized = run(repo, ['state', 'init', changeDir]);
  assert.equal(initialized.status, 0, initialized.stderr);
  return { repo, changeDir, base, head };
}

function candidate(fixture, stage, base = fixture.base) {
  const args = ['review', 'candidate', fixture.changeDir, stage, '--json'];
  if (stage === 'final') args.push('--base', base);
  const result = run(fixture.repo, args);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function reviewReport(current, overrides = {}) {
  return {
    stage: current.stage,
    candidate_identity: current.identity,
    verdict: 'Approved',
    findings: [],
    questions: [],
    review_focus: ['scope', 'correctness', 'tests'],
    summary: `The ${current.stage} candidate is approved.`,
    residual_risks: ['Real host acceptance is a separate gate.'],
    ...(current.stage === 'final' ? { review_base: current.review_base } : {}),
    ...overrides,
  };
}

function writePending(fixture, stage, report, mode = 0o644) {
  const path = join(fixture.changeDir, 'reviews', `${stage}-pending-report.json`);
  writeFileSync(path, `${JSON.stringify(report)}\n`, { mode });
  chmodSync(path, mode);
  return path;
}

function record(fixture, stage, current, { mode = 0o644, report = null } = {}) {
  writePending(fixture, stage, report ?? reviewReport(current), mode);
  const args = ['review', 'record', fixture.changeDir, stage, '--json'];
  if (stage === 'final') args.push('--base', current.review_base);
  return run(fixture.repo, args);
}

function approvePlanningStage(fixture, stage) {
  const current = candidate(fixture, stage);
  const recorded = record(fixture, stage, current);
  assert.equal(recorded.status, 0, recorded.stderr);
  return current;
}

describe('ssf review minimal command surface', () => {
  it('supports only candidate, record, and check', () => {
    const fixture = createFixture();
    try {
      const current = candidate(fixture, 'proposal-specs');
      assert.equal(Object.hasOwn(current, 'candidate_graph'), false);
      for (const removed of ['begin', 'cancel', 'resume', 'retry']) {
        const result = run(fixture.repo, [
          'review', removed, fixture.changeDir, 'proposal-specs', '--json',
        ]);
        assert.notEqual(result.status, 0, removed);
      }
      const help = run(fixture.repo, ['--help']);
      assert.match(help.stdout, /review candidate/);
      assert.match(help.stdout, /review record/);
      assert.match(help.stdout, /review check/);
      assert.doesNotMatch(help.stdout, /review (?:begin|cancel|resume|retry)/);
    } finally {
      rmSync(fixture.repo, { recursive: true, force: true });
    }
  });

  it('records and checks 0644 and 0600 fixed inbox reports atomically', () => {
    const fixture = createFixture();
    try {
      const current = candidate(fixture, 'proposal-specs');
      for (const mode of [0o644, 0o600]) {
        const pending = writePending(
          fixture,
          'proposal-specs',
          reviewReport(current, { summary: `Approved from mode ${mode}.` }),
          mode,
        );
        const recorded = run(fixture.repo, [
          'review', 'record', fixture.changeDir, 'proposal-specs', '--json',
        ]);
        assert.equal(recorded.status, 0, recorded.stderr);
        assert.equal(existsSync(pending), false, 'record consumes the fixed inbox');
        const stored = JSON.parse(readFileSync(
          join(fixture.changeDir, 'reviews', 'proposal-specs-current.json'),
          'utf8',
        ));
        assert.equal(stored.summary, `Approved from mode ${mode}.`);
        const checked = run(fixture.repo, [
          'review', 'check', fixture.changeDir, 'proposal-specs', '--json',
        ]);
        assert.equal(checked.status, 0, checked.stderr);
        assert.equal(JSON.parse(checked.stdout).pass, true);
      }
    } finally {
      rmSync(fixture.repo, { recursive: true, force: true });
    }
  });

  it('rejects symlink, directory, path override, traversal, and wrong stage inboxes', () => {
    const fixture = createFixture();
    try {
      const current = candidate(fixture, 'proposal-specs');
      const reviews = join(fixture.changeDir, 'reviews');
      const pending = join(reviews, 'proposal-specs-pending-report.json');
      const external = join(fixture.repo, 'external-report.json');
      writeFileSync(external, JSON.stringify(reviewReport(current)));
      symlinkSync(external, pending);
      let result = run(fixture.repo, [
        'review', 'record', fixture.changeDir, 'proposal-specs', '--json',
      ]);
      assert.notEqual(result.status, 0);
      rmSync(pending);

      mkdirSync(pending);
      result = run(fixture.repo, [
        'review', 'record', fixture.changeDir, 'proposal-specs', '--json',
      ]);
      assert.notEqual(result.status, 0);
      rmSync(pending, { recursive: true });

      result = run(fixture.repo, [
        'review', 'record', fixture.changeDir, 'proposal-specs',
        '--report', '../../external-report.json', '--json',
      ]);
      assert.notEqual(result.status, 0);
      result = run(fixture.repo, [
        'review', 'record', fixture.changeDir, '../proposal-specs', '--json',
      ]);
      assert.notEqual(result.status, 0);
      result = run(fixture.repo, [
        'review', 'record', fixture.changeDir, 'unknown', '--json',
      ]);
      assert.notEqual(result.status, 0);
    } finally {
      rmSync(fixture.repo, { recursive: true, force: true });
    }
  });

  it('keeps workflow state unchanged on Request Changes and allows repair re-review', () => {
    const fixture = createFixture();
    try {
      const before = run(fixture.repo, [
        'state', 'get', fixture.changeDir, 'state', '--json',
      ]).stdout;
      let current = candidate(fixture, 'proposal-specs');
      let result = record(fixture, 'proposal-specs', current, {
        report: reviewReport(current, {
          verdict: 'Request Changes',
          findings: [{
            severity: 'High',
            file: 'proposal.md',
            line: 2,
            impact: 'Scope is incomplete.',
            suggested_repair: 'Complete the scope.',
          }],
        }),
      });
      assert.equal(result.status, 0, result.stderr);
      result = run(fixture.repo, [
        'review', 'check', fixture.changeDir, 'proposal-specs', '--json',
      ]);
      assert.equal(result.status, 1);
      assert.equal(JSON.parse(result.stdout).code, 'request-changes');
      const afterRejected = run(fixture.repo, [
        'state', 'get', fixture.changeDir, 'state', '--json',
      ]).stdout;
      assert.equal(afterRejected, before);

      writeFileSync(
        join(fixture.changeDir, 'proposal.md'),
        '# Proposal\nThree review stages with explicit repair.\n',
      );
      current = candidate(fixture, 'proposal-specs');
      result = record(fixture, 'proposal-specs', current);
      assert.equal(result.status, 0, result.stderr);
      result = run(fixture.repo, [
        'review', 'check', fixture.changeDir, 'proposal-specs', '--json',
      ]);
      assert.equal(result.status, 0, result.stderr);
    } finally {
      rmSync(fixture.repo, { recursive: true, force: true });
    }
  });
});

describe('recursive stage prerequisites and final base', () => {
  it('keeps downstream approvals stale after each upstream reapproval', () => {
    const fixture = createFixture();
    try {
      const setState = (field, value) => {
        const result = run(fixture.repo, [
          'state', 'set', fixture.changeDir, field, value,
        ]);
        assert.equal(result.status, 0, result.stderr);
      };

      const proposalV1 = approvePlanningStage(fixture, 'proposal-specs');
      setState('dp_1_result', 'confirmed: product direction v1');
      setState('dp_1_candidate_identity', proposalV1.identity);

      const designV1 = approvePlanningStage(fixture, 'design-tasks');
      setState('dp_2_result', 'confirmed: implementation direction v1');
      setState('dp_2_candidate_identity', designV1.identity);

      const finalV1 = candidate(fixture, 'final', fixture.base);
      let result = record(fixture, 'final', finalV1);
      assert.equal(result.status, 0, result.stderr);

      writeFileSync(
        join(fixture.changeDir, 'proposal.md'),
        '# Proposal\nThree review stages with an explicit upstream change.\n',
      );
      const proposalV2 = approvePlanningStage(fixture, 'proposal-specs');
      assert.notEqual(proposalV2.identity, proposalV1.identity);
      setState('dp_1_result', 'confirmed: product direction v2');
      setState('dp_1_candidate_identity', proposalV2.identity);

      const designV2Candidate = candidate(fixture, 'design-tasks');
      assert.notEqual(
        designV2Candidate.identity,
        designV1.identity,
        'Design/Tasks identity must frame the current Approved Proposal/Specs identity',
      );
      result = run(fixture.repo, [
        'review', 'check', fixture.changeDir, 'design-tasks', '--json',
      ]);
      assert.equal(result.status, 1, 'old Design/Tasks approval must remain stale');
      assert.equal(JSON.parse(result.stdout).code, 'stale');
      writePending(fixture, 'design-tasks', reviewReport(designV1));
      result = run(fixture.repo, [
        'review', 'record', fixture.changeDir, 'design-tasks', '--json',
      ]);
      assert.notEqual(result.status, 0, 'record must recompute the chained identity');

      const designV2 = approvePlanningStage(fixture, 'design-tasks');
      assert.equal(designV2.identity, designV2Candidate.identity);
      setState('dp_2_result', 'confirmed: implementation direction v2');
      setState('dp_2_candidate_identity', designV2.identity);

      const finalV2Candidate = candidate(fixture, 'final', fixture.base);
      assert.notEqual(
        finalV2Candidate.identity,
        finalV1.identity,
        'Final identity must frame both current Approved Planning identities',
      );
      result = run(fixture.repo, [
        'review', 'check', fixture.changeDir, 'final', '--base', fixture.base, '--json',
      ]);
      assert.equal(result.status, 1, 'old Final approval must remain stale');
      assert.equal(JSON.parse(result.stdout).code, 'stale');
      writePending(fixture, 'final', reviewReport(finalV1));
      result = run(fixture.repo, [
        'review', 'record', fixture.changeDir, 'final', '--base', fixture.base, '--json',
      ]);
      assert.notEqual(result.status, 0, 'final record must recompute both upstream identities');
    } finally {
      rmSync(fixture.repo, { recursive: true, force: true });
    }
  });

  it('requires current Proposal approval plus DP-1 for all Design/Tasks commands', () => {
    const fixture = createFixture();
    try {
      for (const subcommand of ['candidate', 'record', 'check']) {
        const result = run(fixture.repo, [
          'review', subcommand, fixture.changeDir, 'design-tasks', '--json',
        ]);
        assert.notEqual(result.status, 0, subcommand);
      }

      let proposal = approvePlanningStage(fixture, 'proposal-specs');
      let result = run(fixture.repo, [
        'state', 'set', fixture.changeDir, 'dp_1_result', 'confirmed: product direction',
      ]);
      assert.equal(result.status, 0, result.stderr);
      result = run(fixture.repo, [
        'state', 'set', fixture.changeDir, 'dp_1_candidate_identity', proposal.identity,
      ]);
      assert.equal(result.status, 0, result.stderr);
      assert.equal(candidate(fixture, 'design-tasks').stage, 'design-tasks');

      writeFileSync(join(fixture.changeDir, 'proposal.md'), '# Proposal\nDrifted.\n');
      for (const subcommand of ['candidate', 'record', 'check']) {
        const args = ['review', subcommand, fixture.changeDir, 'design-tasks', '--json'];
        const commandResult = run(fixture.repo, args);
        assert.notEqual(commandResult.status, 0, `stale upstream ${subcommand}`);
      }

      proposal = candidate(fixture, 'proposal-specs');
      result = record(fixture, 'proposal-specs', proposal);
      assert.equal(result.status, 0, result.stderr);
      result = run(fixture.repo, [
        'state', 'set', fixture.changeDir, 'dp_1_candidate_identity', `sha256:${'0'.repeat(64)}`,
      ]);
      assert.equal(result.status, 0, result.stderr);
      result = run(fixture.repo, [
        'review', 'candidate', fixture.changeDir, 'design-tasks', '--json',
      ]);
      assert.notEqual(result.status, 0);
    } finally {
      rmSync(fixture.repo, { recursive: true, force: true });
    }
  });

  it('keeps the first executing commit as the default final base after HEAD advances', () => {
    const fixture = createFixture();
    try {
      const proposal = approvePlanningStage(fixture, 'proposal-specs');
      for (const [field, value] of [
        ['dp_1_result', 'confirmed: product direction'],
        ['dp_1_candidate_identity', proposal.identity],
      ]) {
        const result = run(fixture.repo, ['state', 'set', fixture.changeDir, field, value]);
        assert.equal(result.status, 0, result.stderr);
      }
      const design = approvePlanningStage(fixture, 'design-tasks');
      for (const [field, value] of [
        ['dp_2_result', 'confirmed: implementation direction'],
        ['dp_2_candidate_identity', design.identity],
      ]) {
        const result = run(fixture.repo, ['state', 'set', fixture.changeDir, field, value]);
        assert.equal(result.status, 0, result.stderr);
      }

      for (const args of [
        ['state', 'set', fixture.changeDir, 'workflow', 'tweak'],
        ['state', 'transition', fixture.changeDir, 'approved-for-build'],
        ['state', 'set', fixture.changeDir, 'dp_4_result', 'inline execution'],
        ['state', 'transition', fixture.changeDir, 'executing'],
      ]) {
        const transition = run(fixture.repo, args);
        assert.equal(transition.status, 0, transition.stderr);
      }
      assert.equal(
        run(fixture.repo, ['state', 'get', fixture.changeDir, 'execution_base_commit']).stdout.trim(),
        fixture.head,
      );
      write(fixture.repo, 'src/after-execution.mjs', 'export const afterExecution = true;\n');
      git(fixture.repo, ['add', 'src/after-execution.mjs']);
      git(fixture.repo, ['commit', '-qm', 'implementation after execution start']);
      assert.notEqual(git(fixture.repo, ['rev-parse', 'HEAD']), fixture.head);

      let result = run(fixture.repo, [
        'review', 'candidate', fixture.changeDir, 'final', '--json',
      ]);
      assert.equal(result.status, 0, result.stderr);
      const finalCandidate = JSON.parse(result.stdout);
      assert.equal(finalCandidate.review_base, fixture.head);

      writePending(fixture, 'final', reviewReport(finalCandidate));
      result = run(fixture.repo, [
        'review', 'record', fixture.changeDir, 'final', '--json',
      ]);
      assert.equal(result.status, 0, result.stderr);
      result = run(fixture.repo, [
        'review', 'check', fixture.changeDir, 'final', '--json',
      ]);
      assert.equal(result.status, 0, result.stderr);
      result = run(fixture.repo, [
        'review', 'check', fixture.changeDir, 'final', '--base', fixture.base, '--json',
      ]);
      assert.equal(result.status, 1);

      writeFileSync(join(fixture.repo, 'src/feature.mjs'), 'export const ready = false;\n');
      result = run(fixture.repo, [
        'review', 'check', fixture.changeDir, 'final', '--json',
      ]);
      assert.equal(result.status, 1);
      assert.equal(JSON.parse(result.stdout).code, 'stale');
    } finally {
      rmSync(fixture.repo, { recursive: true, force: true });
    }
  });
});

function run(cwd, args) {
  return spawnSync(process.execPath, [CLI, ...args], {
    cwd,
    encoding: 'utf8',
  });
}

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
