import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const PLUGIN = join(ROOT, '.opencode', 'plugins', 'spec-superflow.js');

function assertNoUnconditionalPlanningReviewLanguage(content) {
  const normalized = content.replace(/\s+/g, ' ');
  const redGreenSentences = normalized
    .split(/(?<=[.!?])\s+/)
    .filter(sentence => /\bRED\b/i.test(sentence) && /\bGREEN\b/i.test(sentence));
  for (const sentence of redGreenSentences) {
    assert.match(sentence, /behavior-changing/i);
  }
  assert.doesNotMatch(
    normalized,
    /(?:every|all)\s+user-visible[^.]{0,200}(?:user action|interaction)/i,
  );
  assert.doesNotMatch(normalized, /\bRun (?:the )?AC tests\b/i);
}

function assertTextInOrder(content, fragments, label) {
  let cursor = -1;
  for (const fragment of fragments) {
    const next = content.indexOf(fragment, cursor + 1);
    assert.notEqual(next, -1, `${label} must contain ${JSON.stringify(fragment)}`);
    assert.equal(next > cursor, true, `${label} must keep ${JSON.stringify(fragment)} in order`);
    cursor = next;
  }
}

async function configured(initial = {}) {
  const module = await import(`${PLUGIN}?test=${Date.now()}-${Math.random()}`);
  const hooks = await module.SpecSuperflowPlugin();
  const config = structuredClone(initial);
  await hooks.config(config);
  return { hooks, config };
}

describe('OpenCode Plugin independent review topology', () => {
  it('registers one Primary, one bootstrap-only setup worker, and one behavior-read-only Reviewer', async () => {
    const { config } = await configured();
    assert.deepEqual(Object.keys(config.agent).sort(), [
      'spec-superflow',
      'spec-superflow-reviewer',
      'spec-superflow-setup',
    ]);
    assert.equal(config.agent['spec-superflow'].mode, 'primary');
    assert.deepEqual(config.agent['spec-superflow'].permission.task, {
      '*': 'deny',
      'spec-superflow-reviewer': 'allow',
    });
    assert.equal(config.agent['spec-superflow'].permission['spec-superflow_*'], 'deny');
    assert.equal(
      Object.hasOwn(config.agent['spec-superflow-reviewer'], 'permission'),
      false,
    );
    assert.equal(config.agent['spec-superflow-reviewer'].hidden, true);
    assert.equal(config.agent['spec-superflow-setup'].permission.question, 'allow');
    assert.equal(config.agent['spec-superflow-setup'].permission['spec-superflow_*'], 'allow');
  });

  it('runs /workflow-init directly as setup without returning a subtask result to Primary', async () => {
    const { config } = await configured();
    assert.deepEqual(config.command['workflow-init'], {
      description: 'Initialize or update the Spec Superflow workflow runtime.',
      agent: 'spec-superflow-setup',
      subtask: false,
      template: config.command['workflow-init'].template,
    });
    assert.match(
      readFileSync(join(ROOT, '.opencode', 'commands', 'workflow-init.md'), 'utf8'),
      /^subtask: false$/m,
    );
    assert.match(config.command['workflow-init'].template, /spec_superflow_cli_status/);
    assert.match(config.command['workflow-init'].template, /spec_superflow_install_cli/);
    assert.match(config.agent['spec-superflow'].prompt, /Ordinary requests never call[\s\S]*bootstrap MCP/i);
  });

  it('uses one fresh Reviewer task per stage and resumes it once for same-stage re-review', async () => {
    const { config } = await configured();
    const primary = config.agent['spec-superflow'].prompt;
    const reviewer = config.agent['spec-superflow-reviewer'].prompt;
    const normalizedPrimary = primary.replace(/\s+/g, ' ');
    const normalizedReviewer = reviewer.replace(/\s+/g, ' ');
    assert.match(primary, /Start one fresh `task` targeting exactly[\s\S]*spec-superflow-reviewer/i);
    assert.match(
      primary,
      /capture[\s\S]*returned `task_id`[\s\S]*Primary[\s\S]*current runtime context/i,
    );
    assert.match(
      primary,
      /first[\s\S]*`Request Changes`[\s\S]*repair[\s\S]*exactly once/i,
    );
    assert.match(primary, /resume[\s\S]*same Reviewer task[\s\S]*same `task_id`/i);
    assert.match(
      primary,
      /second[\s\S]*`Request Changes`[\s\S]*new Finding[\s\S]*malformed[\s\S]*unavailable[\s\S]*nonzero[\s\S]*`BLOCKED`/i,
    );
    assert.match(primary, /never start a third review/i);
    assert.match(primary, /(?:do not|never|or) progress workflow state/i);
    assert.match(
      primary,
      /never write[\s\S]*`task_id`[\s\S]*(?:Review|candidate|workflow-state) artifact/i,
    );
    assertTextInOrder(normalizedPrimary, [
      'The first action after every Reviewer return',
      'raw JSON unchanged',
      'The immediately next action',
      'ssf review record <change-dir> <stage> --json',
      'Immediately after record',
      'ssf review check <change-dir> <stage> --json',
      'Only after write, record, and check',
    ], 'OpenCode raw review return sequence');
    assert.match(
      primary,
      /short reference index containing only[\s\S]*exact candidate JSON[\s\S]*project-relative paths[\s\S]*path plus symbol[\s\S]*command, exit code, and concise result/i,
    );
    assert.match(
      primary,
      /Never inline or[\s\S]*tracked diff[\s\S]*untracked source text[\s\S]*whole artifact[\s\S]*evidence log/i,
    );
    assert.match(
      primary,
      /questions\[0\][\s\S]*upstream_conflict:[\s\S]*do not edit Design or Tasks[\s\S]*explicit Proposal and Specs reopen/i,
    );
    assert.match(reviewer, /initial invocation[\s\S]*fresh independent/i);
    assert.match(
      reviewer,
      /every invocation[\s\S]*reread[\s\S]*exact current candidate[\s\S]*complete[\s\S]*Review Focus/i,
    );
    assert.match(reviewer, /read-only semantic review/i);
    assert.match(reviewer, /ordinary project-read and terminal tools/i);
    assert.match(reviewer, /git status[\s\S]*git diff <review-base>/i);
    assertTextInOrder(normalizedReviewer, [
      '1. **Upstream Scenario overlap preflight**',
      '2. **AC ownership and proof**',
      '3. **User-triggered rendered control**',
      '4. **Visible and accessibility results**',
      '5. **Static selector versus runtime proof**',
      '6. **File Changes honesty**',
      '7. **Decisions**',
      '8. **Batches and dependencies**',
    ], 'resolved OpenCode Reviewer scan');
    assert.match(
      reviewer,
      /getQuantityString\(0\/1\/2\)[\s\S]*does not prove static[\s\S]*quantity="zero"[\s\S]*quantity="one"[\s\S]*quantity="other"/i,
    );
    assertNoUnconditionalPlanningReviewLanguage(reviewer);
    for (const removed of [
      /session protocol/i,
      /state next/i,
      /state confirm/i,
      /review begin/i,
      /review cancel/i,
      /candidate_graph/i,
      /message_graph/i,
      /handoff_attestation/i,
      /repair[-_ ]delta/i,
    ]) {
      assert.doesNotMatch(`${primary}\n${reviewer}`, removed);
    }
  });

  it('registers bundled Skills and a local bootstrap MCP idempotently', async () => {
    const existing = {
      skills: { paths: ['/existing/skills'] },
      mcp: {
        'spec-superflow': { type: 'remote', url: 'https://internal.invalid/mcp' },
      },
    };
    const { hooks, config } = await configured(existing);
    await hooks.config(config);
    assert.equal(new Set(config.skills.paths).size, config.skills.paths.length);
    assert.equal(config.skills.paths.includes('/existing/skills'), true);
    assert.equal(config.skills.paths.filter(path => path !== '/existing/skills').length, 1);
    assert.deepEqual(config.mcp['spec-superflow'], existing.mcp['spec-superflow']);
  });

  it('keeps Reviewer output bound to current artifacts and exact typed verdict', async () => {
    const { config } = await configured();
    const reviewer = config.agent['spec-superflow-reviewer'].prompt;
    assert.match(
      reviewer,
      /project-relative paths to `user-intent\.md`[\s\S]*current artifacts[\s\S]*project standards/i,
    );
    assert.match(reviewer, /candidate_identity/);
    assert.match(reviewer, /allowed_finding_paths/);
    assert.match(reviewer, /Approved or Request Changes/);
    assert.match(reviewer, /severity[\s\S]*file[\s\S]*line[\s\S]*impact[\s\S]*suggested_repair/i);
  });

  it('keeps the central Plugin export free of planning-write policy hooks', () => {
    const source = readFileSync(PLUGIN, 'utf8');
    assert.doesNotMatch(source, /tool\.execute|permission\.ask|state next|state confirm|pending review/i);
    assert.match(source, /config\.agent\['spec-superflow-reviewer'\]/);
    assert.match(source, /config\.command\['workflow-init'\]/);
  });
});
