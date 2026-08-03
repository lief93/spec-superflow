import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { it } from 'node:test';

import { collectWorktreeReviewCandidate } from '../../scripts/lib/worktree-review-candidate.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const OPENCODE_VERSION = '1.14.48';

function debugAgent(cwd, home, name) {
  const result = spawnSync('opencode', ['debug', 'agent', name], {
    cwd,
    encoding: 'utf8',
    env: {
      ...process.env,
      HOME: home,
      XDG_CONFIG_HOME: join(home, 'config'),
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

function debugConfig(cwd, home) {
  const result = spawnSync('opencode', ['debug', 'config'], {
    cwd,
    encoding: 'utf8',
    env: {
      ...process.env,
      HOME: home,
      XDG_CONFIG_HOME: join(home, 'config'),
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

function debugTool(cwd, home, name, tool, params) {
  const result = spawnSync('opencode', [
    'debug',
    'agent',
    name,
    '--tool',
    tool,
    '--params',
    JSON.stringify(params),
  ], {
    cwd,
    encoding: 'utf8',
    env: {
      ...process.env,
      HOME: home,
      XDG_CONFIG_HOME: join(home, 'config'),
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const output = JSON.parse(result.stdout);
  assert.equal(output.tool, tool);
  return output.result;
}

function resolvedPermission(agent, permission, pattern) {
  let action = null;
  for (const rule of agent.permission) {
    if (
      rule.permission === permission
      && (rule.pattern === '*' || rule.pattern === pattern)
    ) {
      action = rule.action;
    }
  }
  return action;
}

function enabledTools(agent) {
  return Object.entries(agent.tools)
    .filter(([, enabled]) => enabled)
    .map(([name]) => name)
    .sort();
}

function assertTextInOrder(content, fragments, label) {
  const normalized = content.replace(/\s+/g, ' ');
  let cursor = -1;
  for (const fragment of fragments) {
    const next = normalized.indexOf(fragment, cursor + 1);
    assert.notEqual(next, -1, `${label} must contain ${JSON.stringify(fragment)}`);
    assert.equal(next > cursor, true, `${label} must keep ${JSON.stringify(fragment)} in order`);
    cursor = next;
  }
}

it('resolves hidden Agent tools through pinned OpenCode for repository and packed Plugin contexts', () => {
  const temp = mkdtempSync(join(tmpdir(), 'ssf-opencode-resolved-tools-'));
  const home = join(temp, 'home');
  const extract = join(temp, 'extract');
  mkdirSync(home, { recursive: true });
  mkdirSync(extract, { recursive: true });

  try {
    const version = spawnSync('opencode', ['--version'], { encoding: 'utf8' });
    assert.equal(version.status, 0, version.stderr || version.stdout);
    assert.equal(version.stdout.trim(), OPENCODE_VERSION);

    const packOutput = JSON.parse(execFileSync(
      'npm',
      ['pack', '--json', '--pack-destination', temp],
      { cwd: ROOT, encoding: 'utf8' },
    ));
    const archive = join(temp, basename(packOutput[0].filename));
    execFileSync('tar', ['-xzf', archive, '-C', extract]);
    const contexts = [ROOT, join(extract, 'package')];

    for (const cwd of contexts) {
      const reviewer = debugAgent(cwd, home, 'spec-superflow-reviewer');
      const reviewerTools = enabledTools(reviewer);
      for (const tool of ['bash', 'glob', 'grep', 'read']) {
        assert.equal(reviewerTools.includes(tool), true, `${cwd} Reviewer ${tool}`);
      }
      assert.match(
        reviewer.prompt,
        /initial invocation[\s\S]*fresh independent review[\s\S]*resumed same-stage/i,
      );
      assert.match(reviewer.prompt, /candidate_identity[\s\S]*allowed_finding_paths/i);
      assert.match(reviewer.prompt, /every invocation[\s\S]*reread[\s\S]*exact current candidate[\s\S]*complete[\s\S]*Review Focus/i);
      assert.match(
        reviewer.prompt,
        /project-relative paths to `user-intent\.md`[\s\S]*current artifacts[\s\S]*project standards/i,
      );
      assert.match(
        reviewer.prompt,
        /git status --short[\s\S]*git diff <review-base>[\s\S]*git log --oneline[\s\S]*git show <review-base>/i,
      );
      assert.match(
        reviewer.prompt,
        /changed_files[\s\S]*outside\s+the current Change directory[\s\S]*Change artifacts[\s\S]*inputs[\s\S]*upstream candidate\s+identit/i,
      );
      assert.match(
        reviewer.prompt,
        /must not[\s\S]*(?:Request Changes|candidate inconsistency)[\s\S]*git status[\s\S]*current Change directory/i,
      );
      assertTextInOrder(reviewer.prompt, [
        '1. **Upstream Scenario overlap preflight**',
        '2. **AC ownership and proof**',
        '3. **User-triggered rendered control**',
        '4. **Visible and accessibility results**',
        '5. **Static selector versus runtime proof**',
        '6. **File Changes honesty**',
        '7. **Decisions**',
        '8. **Batches and dependencies**',
      ], `${cwd} resolved Reviewer scan`);
      assert.match(
        reviewer.prompt,
        /getQuantityString\(0\/1\/2\)[\s\S]*does not prove static[\s\S]*quantity="zero"[\s\S]*quantity="one"[\s\S]*quantity="other"/i,
      );
      assert.doesNotMatch(reviewer.prompt, /session protocol|candidate_graph|message_graph|handoff_attestation|repair[-_ ]delta/i);

      const setup = debugAgent(cwd, home, 'spec-superflow-setup');
      assert.deepEqual(enabledTools(setup), ['question']);
      assert.equal(
        setup.permission.some(rule =>
          rule.permission === 'spec-superflow_*' && rule.action === 'allow'),
        true,
      );

      const primary = debugAgent(cwd, home, 'spec-superflow');
      assert.equal(
        resolvedPermission(primary, 'task', 'spec-superflow-reviewer'),
        'allow',
      );
      for (const deniedAgent of [
        'general',
        'explore',
        'spec-superflow-setup',
      ]) {
        assert.equal(resolvedPermission(primary, 'task', deniedAgent), 'deny');
      }
      assert.match(
        primary.prompt,
        /ordinary requests never call[\s\S]*bootstrap MCP/i,
      );
      assert.match(
        primary.prompt,
        /native `question`[\s\S]*DP-0 through DP-4[\s\S]*same turn/i,
      );
      assert.match(
        primary.prompt,
        /short reference index containing only[\s\S]*exact candidate JSON[\s\S]*project-relative paths[\s\S]*path plus symbol[\s\S]*command, exit code, and concise result/i,
      );
      assert.match(
        primary.prompt,
        /Final handoff[\s\S]*review_base[\s\S]*worktree_identity[\s\S]*changed_files[\s\S]*suggested read-only Git commands/i,
      );
      assert.match(
        primary.prompt,
        /changed_files[\s\S]*outside\s+the current Change directory[\s\S]*Change artifacts[\s\S]*inputs[\s\S]*upstream candidate\s+identit/i,
      );
      assert.match(
        primary.prompt,
        /Never inline or[\s\S]*tracked diff[\s\S]*untracked source text[\s\S]*whole artifact[\s\S]*evidence log/i,
      );
      assertTextInOrder(primary.prompt, [
        'The first action after every Reviewer return',
        'raw JSON unchanged',
        'The immediately next action',
        'ssf review record <change-dir> <stage> --json',
        'Immediately after record',
        'ssf review check <change-dir> <stage> --json',
        'Only after write, record, and check',
      ], `${cwd} resolved Primary review return sequence`);
      assert.match(
        primary.prompt,
        /Missing any one of write, record, or check[\s\S]*`BLOCKED`[\s\S]*Only that exact check result[\s\S]*verified blocking verdict/i,
      );
      assert.match(
        primary.prompt,
        /questions\[0\][\s\S]*upstream_conflict:[\s\S]*do not edit Design or Tasks[\s\S]*explicit Proposal and Specs reopen/i,
      );
      assert.match(
        primary.prompt,
        /resume the same Reviewer task[\s\S]*same `task_id`[\s\S]*reread and completely review the new candidate/i,
      );
      assert.match(
        primary.prompt,
        /second verified result[\s\S]*Request Changes[\s\S]*immediately report `BLOCKED`[\s\S]*Never start a third review/i,
      );
      assert.doesNotMatch(primary.prompt, /state next|state confirm|review begin|review cancel|candidate_graph|message_graph|handoff_attestation|repair[-_ ]delta/i);

      const config = debugConfig(cwd, home);
      assert.equal(config.command['workflow-init'].agent, 'spec-superflow-setup');
      assert.equal(config.command['workflow-init'].subtask, false);
    }

    const runtimeRepo = join(temp, 'reviewer-runtime-repo');
    cpSync(join(extract, 'package'), runtimeRepo, { recursive: true });
    git(runtimeRepo, ['init', '-q', '-b', 'main']);
    git(runtimeRepo, ['config', 'user.email', 'tests@example.com']);
    git(runtimeRepo, ['config', 'user.name', 'Spec Superflow Tests']);
    git(runtimeRepo, ['add', '.']);
    git(runtimeRepo, ['commit', '-qm', 'baseline']);
    const reviewBase = git(runtimeRepo, ['rev-parse', 'HEAD']).trim();
    const trackedSentinel = 'OPENCODE_REVIEWER_TRACKED_DIFF_SENTINEL';
    const untrackedSentinel = 'OPENCODE_REVIEWER_UNTRACKED_READ_SENTINEL';
    writeFileSync(join(runtimeRepo, 'README.md'), `${trackedSentinel}\n`);
    writeFileSync(join(runtimeRepo, 'review-untracked.txt'), `${untrackedSentinel}\n`);
    const changeDir = join(runtimeRepo, 'changes', 'probe');
    mkdirSync(changeDir, { recursive: true });

    const before = collectWorktreeReviewCandidate({
      repoRoot: runtimeRepo,
      changeDir,
      base: reviewBase,
    });
    const statusBefore = git(runtimeRepo, [
      'status',
      '--porcelain=v2',
      '-z',
      '--untracked-files=all',
    ]);
    const stagedBefore = git(runtimeRepo, ['diff', '--cached', '--binary']);

    const statusResult = debugTool(
      runtimeRepo,
      home,
      'spec-superflow-reviewer',
      'bash',
      { command: 'git status --short', description: 'Inspect frozen worktree status' },
    );
    assert.equal(statusResult.metadata.exit, 0);
    assert.match(statusResult.output, /M README\.md/);
    assert.match(statusResult.output, /\?\? review-untracked\.txt/);

    const diffResult = debugTool(
      runtimeRepo,
      home,
      'spec-superflow-reviewer',
      'bash',
      {
        command: `git diff ${reviewBase} -- README.md`,
        description: 'Inspect fixed-base tracked diff',
      },
    );
    assert.equal(diffResult.metadata.exit, 0);
    assert.match(diffResult.output, new RegExp(trackedSentinel));

    const logResult = debugTool(
      runtimeRepo,
      home,
      'spec-superflow-reviewer',
      'bash',
      {
        command: `git log --oneline ${reviewBase}..HEAD`,
        description: 'Inspect commits after review base',
      },
    );
    assert.equal(logResult.metadata.exit, 0);

    const showResult = debugTool(
      runtimeRepo,
      home,
      'spec-superflow-reviewer',
      'bash',
      {
        command: `git show ${reviewBase}:README.md`,
        description: 'Inspect base file content',
      },
    );
    assert.equal(showResult.metadata.exit, 0);
    assert.doesNotMatch(showResult.output, new RegExp(trackedSentinel));

    const readResult = debugTool(
      runtimeRepo,
      home,
      'spec-superflow-reviewer',
      'read',
      { filePath: join(runtimeRepo, 'review-untracked.txt') },
    );
    assert.match(readResult.output, new RegExp(untrackedSentinel));

    const after = collectWorktreeReviewCandidate({
      repoRoot: runtimeRepo,
      changeDir,
      base: reviewBase,
    });
    assert.equal(after.identity, before.identity);
    assert.equal(
      git(runtimeRepo, ['status', '--porcelain=v2', '-z', '--untracked-files=all']),
      statusBefore,
    );
    assert.equal(git(runtimeRepo, ['diff', '--cached', '--binary']), stagedBefore);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

function git(cwd, args) {
  return execFileSync('git', ['-C', cwd, ...args], {
    encoding: 'utf8',
  });
}
