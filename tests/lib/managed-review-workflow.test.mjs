import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const read = path => readFileSync(join(ROOT, path), 'utf8');
const primary = read('agents/spec-superflow.agent.md');
const reviewer = read('agents/spec-superflow-reviewer.agent.md');
const openCodePrimary = read('.opencode/agents/spec-superflow.md');
const openCodeReviewer = read('.opencode/agents/spec-superflow-reviewer.md');
const workflowStart = read('skills/workflow-start/SKILL.md');
const specWriter = read('skills/spec-writer/SKILL.md');
const contractBuilder = read('skills/contract-builder/SKILL.md');
const buildExecutor = read('skills/build-executor/SKILL.md');
const releaseArchivist = read('skills/release-archivist/SKILL.md');
const vscodeDocs = read('docs/vscode-agent-plugin.md');
const vscodeDocsZh = read('docs/vscode-agent-plugin-zh.md');
const openCodeInstall = read('.opencode/INSTALL.md');

function assertExplicitDeliveryTriggers(content, label) {
  assert.match(
    content,
    /current Specs\s+explicitly\s+require\s+a\s+delivery\s+package/i,
    `${label} must honor a Specs-only delivery-package AC`,
  );
  assert.match(
    content,
    /execution-contract\.md > AC Test Matrix`\s+explicitly\s+requires\s+a\s+delivery\s+package/i,
    `${label} must honor an execution-contract AC delivery package`,
  );
}

function assertNoUnconditionalPlanningReviewLanguage(content, label) {
  const normalized = content.replace(/\s+/g, ' ');
  const redGreenSentences = normalized
    .split(/(?<=[.!?])\s+/)
    .filter(sentence => /\bRED\b/i.test(sentence) && /\bGREEN\b/i.test(sentence));
  for (const sentence of redGreenSentences) {
    assert.match(
      sentence,
      /behavior-changing/i,
      `${label} must condition every RED/GREEN requirement on behavior-changing work`,
    );
  }
  assert.doesNotMatch(
    normalized,
    /(?:every|all)\s+user-visible[^.]{0,200}(?:user action|interaction)/i,
    `${label} must not require user interaction for every user-visible AC`,
  );
  assert.doesNotMatch(
    normalized,
    /\bRun (?:the )?AC tests\b/i,
    `${label} must not accept a generic AC test command`,
  );
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

describe('fixed independent review workflow contract', () => {
  it('keeps one visible Primary and one fixed read-only Reviewer', () => {
    assert.match(primary, /agents: \["Spec Superflow Reviewer"\]/);
    assert.match(primary, /user-invocable: true/i);
    assert.match(primary, /hidden `Spec Superflow Reviewer`/i);
    assert.match(reviewer, /user-invocable: false/);
    assert.doesNotMatch(reviewer, /^tools:/m);
    assert.match(reviewer, /agents: \[\]/);
    assert.match(
      reviewer,
      /Do not edit[^]*stage[^]*commit[^]*push[^]*change workflow state[^]*invoke another Agent/i,
    );
    assert.match(reviewer, /ordinary project-read and terminal tools/i);
  });

  it('uses candidate -> stage-scoped Reviewer -> fixed inbox -> record -> check', () => {
    for (const host of [primary, openCodePrimary]) {
      assert.match(host, /ssf review candidate <change-dir> <stage> --json/i);
      assert.match(host, /one independent Reviewer context|one fresh `task`/i);
      assert.match(host, /reviews\/<stage>-pending-report\.json/);
      assert.match(host, /ssf review record <change-dir> <stage> --json/i);
      assert.match(host, /ssf review check <change-dir> <stage> --json/i);
      assert.match(host, /Request Changes[\s\S]*state unchanged|keep the workflow in its current state/i);
      assert.match(host, /first[\s\S]*Request Changes[\s\S]*repair[\s\S]*(?:exactly )?once/i);
      assert.match(host, /same[\s\S]*Reviewer (?:context|task)[\s\S]*(?:re-review|resume)/i);
      assert.match(host, /second[\s\S]*Request Changes[\s\S]*BLOCKED/i);
      assert.match(host, /never[\s\S]*third review/i);
    }
  });

  it('uses body-free references while Reviewer independently acquires the fixed-base diff', () => {
    for (const [label, host] of [
      ['VS Code Primary', primary],
      ['OpenCode Primary', openCodePrimary],
    ]) {
      assert.match(
        host,
        /Planning handoff[\s\S]*proposal-specs[\s\S]*design-tasks[\s\S]*short reference index/i,
        `${label} must scope bounded references to Planning`,
      );
      assert.match(
        host,
        /exact candidate JSON unchanged[\s\S]*project-relative paths? to `user-intent\.md`[\s\S]*current stage artifacts/i,
        `${label} must pass artifact paths rather than copies`,
      );
      assert.match(
        host,
        /necessary repository and test evidence\s+index[\s\S]*project-relative path[\s\S]*symbol/i,
        `${label} must pass a bounded path and symbol evidence index`,
      );
      assert.match(
        host,
        /exact mechanical check\s+results[\s\S]*command[\s\S]*exit[\s\S]*result/i,
        `${label} must pass exact concise mechanical results`,
      );
      assert.match(
        host,
        /Final handoff[\s\S]*exact final candidate JSON unchanged[\s\S]*review_base[\s\S]*worktree_identity[\s\S]*changed_files[\s\S]*review targets/i,
        `${label} must pass only the final metadata candidate`,
      );
      assert.match(
        host,
        /suggested read-only Git commands[\s\S]*git status[\s\S]*git diff <review-base>[\s\S]*git log[\s\S]*git show/i,
        `${label} must suggest standard Reviewer-owned SCM reads`,
      );
      assert.match(
        host,
        /never (?:inline|add)[\s\S]*tracked diff[\s\S]*untracked source text[\s\S]*whole artifact[\s\S]*evidence log/i,
        `${label} must prohibit all Primary body copies`,
      );
      assert.match(
        host,
        /record[\s\S]*check[\s\S]*(?:status|staged)[\s\S]*worktree[\s\S]*(?:unchanged|drift)/i,
        `${label} must verify Reviewer left the frozen Git state unchanged`,
      );
    }
    assert.match(
      reviewer,
      /For `proposal-specs` and[\s\S]*`design-tasks`[\s\S]*project-relative paths[\s\S]*Open and inspect those paths/i,
      'Reviewer must resolve bounded Planning references itself',
    );
    assert.match(
      reviewer,
      /For `final`[\s\S]*run `git status[\s\S]*git diff <review-base>[\s\S]*git log[\s\S]*git show[\s\S]*every\s+`changed_files` entry[\s\S]*untracked[\s\S]*read/i,
      'Reviewer must acquire and inspect tracked and untracked final content itself',
    );
    assert.doesNotMatch(`${primary}\n${openCodePrimary}`, /candidate JSON[^]*raw tracked diff/i);
  });

  it('defines final changed_files as implementation diff outside the current Change', () => {
    for (const [label, host] of [
      ['VS Code Primary', primary],
      ['OpenCode Primary', openCodePrimary],
    ]) {
      assert.match(
        host,
        /changed_files[^]*outside\s+the current Change directory[^]*Change artifacts[^]*inputs[^]*upstream candidate\s+identit/i,
        `${label} must explain the final candidate scope to Reviewer`,
      );
    }
    assert.match(
      reviewer,
      /changed_files[^]*outside\s+the current Change directory[^]*Change artifacts[^]*inputs[^]*upstream candidate\s+identit/i,
      'Reviewer must distinguish implementation diff from separately bound Change artifacts',
    );
    assert.match(
      reviewer,
      /must not[^]*(?:Request Changes|candidate inconsistency)[^]*git status[^]*current Change directory/i,
      'Reviewer must not reject a candidate merely because the current Change directory appears in Git status',
    );
  });

  it('makes raw -> record -> check the only legal return sequence', () => {
    for (const [label, host] of [
      ['VS Code Primary', primary],
      ['OpenCode Primary', openCodePrimary],
      ['workflow-start', workflowStart],
    ]) {
      assertTextInOrder(host.replace(/\s+/g, ' '), [
        'The first action after every Reviewer return',
        'raw JSON',
        'unchanged to',
        'The immediately next action',
        'ssf review record <change-dir> <stage> --json',
        'Immediately after record',
        'ssf review check <change-dir> <stage> --json',
        'Only after write, record, and check',
      ], label);
      assert.match(
        host,
        /before all three finish[^]*do not\s+interpret[^]*edit[^]*invoke (?:Reviewer|another review|task)/i,
        `${label} must forbid semantic handling before durable CLI validation`,
      );
      assert.match(
        host,
        /missing any one of write, record, or check[^]*BLOCKED/i,
        `${label} must fail closed when a return step is skipped`,
      );
      assert.match(
        host,
        /check[^]*nonzero[^]*code[^]*request-changes[^]*verified blocking verdict[^]*preserve[^]*current\s+evidence/i,
        `${label} must distinguish a verified Request Changes result from transport failure`,
      );
    }
  });

  it('keeps all removed orchestration and attestation protocols absent', () => {
    const hostContract = [primary, reviewer, openCodePrimary, openCodeReviewer].join('\n');
    for (const removed of [
      /ssf state next/i,
      /ssf state confirm/i,
      /ssf review begin/i,
      /ssf review cancel/i,
      /candidate_graph/i,
      /message_graph/i,
      /handoff_attestation/i,
      /repair[-_ ]delta/i,
      /confirmation[-_ ]receipt/i,
      /orchestration_mode/i,
      /managed-independent-review/i,
    ]) {
      assert.doesNotMatch(hostContract, removed);
    }
    assert.doesNotMatch(`${primary}\n${reviewer}`, /task_id/i);
  });

  it('separates the two Planning reviews from user DP-1/DP-2 and contract DP-3', () => {
    assert.match(primary, /proposal-specs[\s\S]*ssf review check[\s\S]*goals, scope, behaviors, and non-goals/i);
    assert.match(primary, /dp_1_result[\s\S]*dp_1_candidate_identity/);
    assert.match(primary, /design-tasks[\s\S]*reviewed\s+design, batches, and test plan/i);
    assert.match(primary, /dp_2_result[\s\S]*dp_2_candidate_identity/);
    assert.match(primary, /Only then may `contract-builder`[\s\S]*DP-2[\s\S]*DP-3[\s\S]*separate/i);
  });

  it('keeps final semantic review after mechanics and before the single closing transition', () => {
    assert.match(primary, /`final`:[\s\S]*implementation, tests, applicable runtime evidence[\s\S]*PR summary[\s\S]*complete and frozen/i);
    assert.match(primary, /one stable Git base[\s\S]*same `--base <review-base>`/i);
    assert.match(primary, /After current final[\s\S]*Approved[\s\S]*no substantive write/i);
    assert.match(primary, /release-archivist[\s\S]*state get <change-dir> state[\s\S]*exactly `closing`/i);
  });

  it('keeps delivery-package evidence optional for an ordinary full Story', () => {
    const preReview = /### Pre-review preparation([\s\S]*?)(?=### Post-approval state progression)/
      .exec(releaseArchivist)?.[1] || '';
    assert.match(preReview, /must contain these\s+three exact rows/i);
    assert.match(preReview, /- `Artifact validate`:/);
    assert.match(preReview, /- `State check`:/);
    assert.match(preReview, /- `Runtime acceptance`:/);
    assert.doesNotMatch(
      preReview,
      /`Delivery package`|package SHA-256|entry count|hygiene result/i,
    );
    assertExplicitDeliveryTriggers(preReview, 'release-archivist');

    for (const [label, surface] of [
      ['VS Code Primary', primary],
      ['workflow-start', workflowStart],
      ['OpenCode Primary', openCodePrimary],
      ['OpenCode install', openCodeInstall],
      ['English workflow docs', vscodeDocs],
    ]) {
      assertExplicitDeliveryTriggers(surface, label);
    }
    assert.match(vscodeDocsZh, /当前 Specs 明确要求交付包/);
    assert.match(
      vscodeDocsZh,
      /execution-contract\.md > AC Test Matrix` 明确要求交付包/,
    );

    const ordinaryWorkflow = [primary, openCodePrimary, workflowStart, vscodeDocs, vscodeDocsZh, openCodeInstall]
      .join('\n');
    assert.doesNotMatch(
      ordinaryWorkflow,
      /runtime\/package evidence|mechanical\/package\/runtime|every mechanical, package, delivery|全部机械门禁、包检查|schema\/state\/test\/package checks/i,
    );
  });

  it('keeps hotfix/tweak and ordinary runtime behavior outside review/bootstrap', () => {
    for (const host of [primary, openCodePrimary]) {
      assert.match(host, /hotfix.*tweak/i);
      assert.match(host, /exact `?(?:workflow[=:]\s*)?full`?[\s\S]*(?:independent semantic review|Reviewer)|independent semantic review[\s\S]*exact `?(?:workflow[=:]\s*)?full`?/i);
      assert.match(host, /global `ssf`/i);
    }
    assert.match(primary, /Workflow Skills[\s\S]*must not call[\s\S]*bootstrap MCP tools/i);
    assert.match(openCodePrimary, /Ordinary requests never call[\s\S]*bootstrap MCP tools/i);
  });

  it('makes Reviewer semantic and evidence-first without replacing mechanical gates', () => {
    assert.match(
      reviewer,
      /project-relative paths[\s\S]*Open and inspect those paths before deciding/i,
    );
    assert.match(reviewer, /Structural validation is not\s+semantic approval/i);
    assert.match(reviewer, /Aggregate test counts are not proof/i);
    assert.match(reviewer, /Do not rerun mechanical gates/i);
    assert.match(reviewer, /Critical, High, and Medium Findings block/i);
    assert.match(reviewer, /line.*positive integer/i);
    assert.doesNotMatch(reviewer, /unknown line|line.*null|null.*line/i);
  });

  it('closes Proposal and Specs against intent before first review', () => {
    const proposalStage = /For the Proposal and Specs stage:([\s\S]*?)(?=After `ssf review check)/
      .exec(specWriter)?.[1] || '';
    assert.match(
      proposalStage,
      /item by item[\s\S]*explicit behavior[\s\S]*constraint[\s\S]*verifiable[\s\S]*proposal\.md[\s\S]*Specs/i,
    );
    assert.match(
      proposalStage,
      /state[\s\S]*variant[\s\S]*parallel[\s\S]*surface[\s\S]*visible[\s\S]*accessibility/i,
    );
    assert.match(
      proposalStage,
      /reus(?:e|ing)[\s\S]*existing[\s\S]*(?:entry|trigger)[\s\S]*inspect[\s\S]*real repository[\s\S]*evidence/i,
    );
    assert.match(
      proposalStage,
      /user-intent\.md[\s\S]*explicitly\s+(?:authorizes|requires)[\s\S]*new[\s\S]*(?:entry|control|trigger)[\s\S]*allow[\s\S]*location[\s\S]*trigger\s+action[\s\S]*verifiable\s+result/i,
    );
    assert.match(
      proposalStage,
      /without[\s\S]*user-intent\.md[\s\S]*(?:authority|basis)[\s\S]*(?:do not|never)[\s\S]*(?:invent|assume)/i,
    );
    assert.match(
      proposalStage,
      /repair[\s\S]*missing[\s\S]*before[\s\S]*(?:freeze|Reviewer)/i,
    );
    assert.match(
      proposalStage,
      /compare[\s\S]*Scenarios?[\s\S]*trigger[\s\S]*outcome[\s\S]*observable surface[\s\S]*acceptance risk[\s\S]*subset or superset[\s\S]*substantially\s+overlap[\s\S]*same test[\s\S]*multiple ACs[\s\S]*(?:merge|narrow)[\s\S]*before[\s\S]*(?:freeze|Reviewer)/i,
    );
    assert.match(
      proposalStage,
      /Primary context[\s\S]*not[\s\S]*new artifact[\s\S]*matrix/i,
    );
  });

  it('makes proposal-specs review return complete intent-closure gaps at first review', () => {
    const proposalFocus = /For `proposal-specs`([\s\S]*?)(?=\nFor `design-tasks`)/
      .exec(reviewer)?.[1] || '';
    const normalized = proposalFocus.replace(/\s+/g, ' ');
    assertTextInOrder(normalized, [
      '1. **Scenario overlap preflight**',
      '2. **Intent closure**',
      '3. **Entry authority**',
      '4. **Scope quality**',
    ], 'proposal-specs fixed scan');
    assert.match(
      proposalFocus,
      /trace[\s\S]*each explicit behavior[\s\S]*constraint[\s\S]*user-intent\.md[\s\S]*proposal\.md[\s\S]*Scenario/i,
    );
    assert.match(
      proposalFocus,
      /state and value variants[\s\S]*parallel visible and accessibility\s+surfaces/i,
    );
    assert.match(
      proposalFocus,
      /claimed reuse[\s\S]*real repository evidence[\s\S]*existing entry or trigger/i,
    );
    assert.match(
      proposalFocus,
      /new entry, control, or trigger only[\s\S]*user-intent\.md` authorizes it[\s\S]*location, trigger action, and verifiable result/i,
    );
    assert.match(
      proposalFocus,
      /complete closure scan[\s\S]*every\s+blocking gap[\s\S]*same initial `findings` array/i,
    );
  });

  it('scales Design and Tasks from the minimum real production seam', () => {
    assert.match(
      specWriter,
      /inspect[\s\S]*real production[\s\S]*existing tests[\s\S]*minimum behavior-changing production seam/i,
    );
    assert.match(
      specWriter,
      /Decision[\s\S]*only when[\s\S]*real architecture choice[\s\S]*trade-off/i,
    );
    assert.match(
      specWriter,
      /multiple Scenarios[\s\S]*same technical choice[\s\S]*(?:reuse|share)[\s\S]*(?:one|single) Decision[\s\S]*No design change/i,
    );
    assert.match(
      specWriter,
      /when no real architecture choice exists[\s\S]*keep `## Decisions`[\s\S]*omit[\s\S]*`### Decision:/i,
    );
    assert.match(
      specWriter,
      /only[\s\S]*production files[\s\S]*behavior must change/i,
    );
    assert.match(
      specWriter,
      /unchanged[\s\S]*(?:Repository|ViewModel)[\s\S]*existing tests[\s\S]*injectable[\s\S]*(?:UI|rendering) seam/i,
    );
    assert.match(
      specWriter,
      /do not (?:create|add)[\s\S]*(?:fake|repository|helper)[\s\S]*retest[\s\S]*unchanged/i,
    );
    assert.match(
      specWriter,
      /fewest Batches[\s\S]*cohesive seam[\s\S]*no cross-batch[\s\S]*one Batch/i,
    );
    assert.match(
      specWriter,
      /shared[\s\S]*production change[\s\S]*(?:one|single)[\s\S]*owner[\s\S]*other ACs[\s\S]*distinct[\s\S]*(?:delta|test)/i,
    );
  });

  it('readies Design and Tasks against real tests and executable evidence before freeze', () => {
    const designStage = /For the Design and Tasks stage,([\s\S]*?)(?=After `ssf review check)/
      .exec(specWriter)?.[1] || '';
    assert.match(
      designStage,
      /review-readiness pass[\s\S]*before[\s\S]*(?:freeze|Reviewer)[\s\S]*Primary context[\s\S]*no new artifact/i,
    );
    assert.match(
      specWriter,
      /read[\s\S]*real test file[\s\S]*exact Test Case[\s\S]*`Update` only[\s\S]*exists[\s\S]*extend[\s\S]*`Add` only[\s\S]*new[\s\S]*`Run existing` only[\s\S]*unchanged/i,
    );
    assert.match(
      specWriter,
      /same[\s\S]*(?:`Run existing`|Test Case)[\s\S]*one AC[\s\S]*extend[\s\S]*`Update`[\s\S]*do not[\s\S]*parallel[\s\S]*`Add`[\s\S]*distinct acceptance risk/i,
    );
    assert.match(
      specWriter,
      /behavior-changing work[\s\S]*RED[\s\S]*GREEN[\s\S]*complete[\s\S]*repository-executable command[\s\S]*real project[\s\S]*class#method[\s\S]*--tests/i,
    );
    assert.match(
      specWriter,
      /coverage-only[\s\S]*characterization[\s\S]*unchanged regression[\s\S]*baseline PASS[\s\S]*rerun[\s\S]*complete[\s\S]*repository-executable command[\s\S]*exact Test Case[\s\S]*(?:never|do not)[\s\S]*(?:manufacture|invent)[\s\S]*RED/i,
    );
    assert.doesNotMatch(
      specWriter,
      /Each AC's TDD Steps must[\s\S]*RED[\s\S]*GREEN/i,
    );
    const tddStepsTemplate = /#### TDD Steps([\s\S]*?)```/.exec(specWriter)?.[1] || '';
    assert.match(
      tddStepsTemplate,
      /choose[\s\S]*applicable branch[\s\S]*behavior-changing[\s\S]*RED[\s\S]*GREEN[\s\S]*coverage-only[\s\S]*BASELINE PASS[\s\S]*RERUN/i,
    );
    assert.match(
      tddStepsTemplate,
      /REFACTOR: Run `<complete repository-executable command selecting the AC tests and relevant regression tests>`/i,
    );
    assert.doesNotMatch(tddStepsTemplate, /REFACTOR: Run the AC tests/i);
    const validationChecklist = /## Validation Checklist([\s\S]*?)(?=\n## Validation Repair Loop)/
      .exec(specWriter)?.[1] || '';
    const tasksChecklist = /### tasks\.md([\s\S]*)/.exec(validationChecklist)?.[1] || '';
    assert.match(
      tasksChecklist,
      /behavior-changing[\s\S]*RED[\s\S]*GREEN[\s\S]*coverage-only[\s\S]*characterization[\s\S]*unchanged regression[\s\S]*BASELINE PASS[\s\S]*RERUN/i,
    );
    assert.match(
      tasksChecklist,
      /both[\s\S]*branches[\s\S]*REFACTOR[\s\S]*complete repository-executable command/i,
    );
    assertNoUnconditionalPlanningReviewLanguage(tasksChecklist, 'tasks Validation Checklist');
    assert.match(
      specWriter,
      /before[\s\S]*freeze[\s\S]*Choice[\s\S]*Rationale[\s\S]*Alternatives[\s\S]*semantically[\s\S]*merge[\s\S]*multiple Scenarios[\s\S]*one Decision[\s\S]*(?:surface|resource)/i,
    );
    assert.match(
      specWriter,
      /`Proves`[\s\S]*only[\s\S]*observable[\s\S]*(?:command|mechanism)[\s\S]*(?:source selector|category)[\s\S]*(?:file-change obligation|File Changes)[\s\S]*not[\s\S]*runtime/i,
    );
    assert.match(
      specWriter,
      /getQuantityString\(0\/1\/2\)[\s\S]*does not prove[\s\S]*quantity="zero"[\s\S]*quantity="one"[\s\S]*quantity="other"[\s\S]*File Changes/i,
    );
    assert.match(
      specWriter,
      /minimum behavior-changing production seam[\s\S]*one cohesive seam[\s\S]*one Batch/i,
    );
    assert.match(
      specWriter,
      /UI row[\s\S]*visible result[\s\S]*only[\s\S]*Scenario WHEN[\s\S]*user-triggered[\s\S]*rendered-control interaction[\s\S]*initial load[\s\S]*lifecycle[\s\S]*(?:external|system) event[\s\S]*injectable seam[\s\S]*visible result/i,
    );
  });

  it('makes design-tasks review reject over-design in one semantic pass', () => {
    const designTasksFocus = /For `design-tasks`([\s\S]*?)(?=\nFor `final`)/
      .exec(reviewer)?.[1] || '';
    assert.match(
      designTasksFocus,
      /inspect[\s\S]*real repository[\s\S]*minimum\s+behavior-changing\s+production\s+seam/i,
    );
    assert.match(
      designTasksFocus,
      /no invented module[\s\S]*unnecessary layer[\s\S]*Repository[\s\S]*fake[\s\S]*helper/i,
    );
    assert.match(
      designTasksFocus,
      /merge\s+semantically duplicate Decisions[\s\S]*reject repeated production changes[\s\S]*unproven scope expansion/i,
    );
    assert.match(
      designTasksFocus,
      /one cohesive seam[\s\S]*one Batch[\s\S]*reject\s+extra Batches[\s\S]*mechanically duplicated rows/i,
    );
    assert.match(
      designTasksFocus,
      /complete related set of blocking findings[\s\S]*same initial `findings`\s+array/i,
    );
    assert.match(
      designTasksFocus,
      /not artifact\s+line count[\s\S]*Scenario count[\s\S]*size tier/i,
    );
  });

  it('makes design-tasks review independently verify executable planning evidence', () => {
    const designTasksFocus = /For `design-tasks`([\s\S]*?)(?=\nFor `final`)/
      .exec(reviewer)?.[1] || '';
    assert.match(
      designTasksFocus,
      /read the real test file and exact Test Case/i,
    );
    assert.match(
      designTasksFocus,
      /`Update` means that exact case exists and is extended[\s\S]*`Add` means a new\s+exact method[\s\S]*distinct acceptance risk[\s\S]*`Run existing` means test\s+and behavior are unchanged/i,
    );
    assert.match(
      designTasksFocus,
      /one Test Case belongs to one AC[\s\S]*reject a\s+synonymous `Add`/i,
    );
    assert.match(
      designTasksFocus,
      /behavior-changing work needs RED and GREEN[\s\S]*complete\s+repository-executable command[\s\S]*real project tooling/i,
    );
    assert.match(
      designTasksFocus,
      /coverage-only, characterization, or unchanged regression needs BASELINE PASS\s+and RERUN[\s\S]*never manufacture RED/i,
    );
    assert.match(
      designTasksFocus,
      /check each Choice, Rationale, and Alternatives[\s\S]*merge\s+semantically duplicate Decisions/i,
    );
    assert.match(
      designTasksFocus,
      /`Proves` may claim only observable\s+results[\s\S]*Android[\s\S]*getQuantityString\(0\/1\/2\)[\s\S]*does not prove static[\s\S]*File Changes as a static obligation/i,
    );
    assert.match(
      designTasksFocus,
      /only a user-triggered Scenario must\s+exercise the real rendered control[\s\S]*injectable seam[\s\S]*visible result/i,
    );
    assertNoUnconditionalPlanningReviewLanguage(designTasksFocus, 'canonical Reviewer');
  });

  it('runs overlap preflight before the fixed Design and Tasks scan', () => {
    const proposalFocus = /For `proposal-specs`([^]*?)(?=\nFor `design-tasks`)/
      .exec(reviewer)?.[1] || '';
    const designTasksFocus = /For `design-tasks`([^]*?)(?=\nFor `final`)/
      .exec(reviewer)?.[1] || '';
    const normalizedProposal = proposalFocus.replace(/\s+/g, ' ');
    const normalizedDesignTasks = designTasksFocus.replace(/\s+/g, ' ');

    assertTextInOrder(normalizedProposal, [
      'Scenario overlap preflight',
      'trigger',
      'outcome',
      'surface',
      'risk',
      'subset or superset',
      'must not be Approved',
    ], 'proposal-specs overlap preflight');
    assertTextInOrder(normalizedDesignTasks, [
      '1. **Upstream Scenario overlap preflight**',
      '2. **AC ownership and proof**',
      '3. **User-triggered rendered control**',
      '4. **Visible and accessibility results**',
      '5. **Static selector versus runtime proof**',
      '6. **File Changes honesty**',
      '7. **Decisions**',
      '8. **Batches and dependencies**',
    ], 'design-tasks fixed scan');
    assert.match(
      designTasksFocus,
      /questions\[0\][^]*upstream_conflict:[^]*do not suggest[^]*(?:Design|Tasks) repair/i,
    );
    assert.match(
      designTasksFocus,
      /getQuantityString\(0\/1\/2\)[^]*does not prove[^]*quantity="zero"[^]*quantity="one"[^]*quantity="other"[^]*File Changes[^]*static obligation/i,
    );
    for (const host of [primary, openCodePrimary]) {
      assert.match(
        host,
        /questions\[0\][^]*upstream_conflict:[^]*do not edit[^]*design[^]*tasks[^]*explicit Proposal and Specs reopen/i,
      );
    }
  });

  it('stops downstream repair and requests explicit reopen for an upstream conflict', () => {
    for (const [label, host] of [
      ['VS Code Primary', primary],
      ['OpenCode Primary', openCodePrimary],
      ['spec-writer', specWriter],
    ]) {
      assert.match(
        host,
        /`upstream_conflict:?`[\s\S]*stop[\s\S]*explicit[\s\S]*reopen[\s\S]*(?:do not|must not)[\s\S]*(?:repair|continue)/i,
        `${label} must fail closed instead of repairing downstream artifacts`,
      );
    }
  });

  it('requires every initial stage review to report the complete blocking set', () => {
    assert.match(
      reviewer,
      /initial review[\s\S]*complete the applicable ordered scan before choosing a\s+verdict/i,
    );
    assert.match(
      reviewer,
      /do not stop after\s+the first Finding or defer a blocking issue to re-review/i,
    );
    assert.match(reviewer, /every blocking\s+Finding[\s\S]*same `findings` array/i);
  });

  it('keeps the shared Skills on the legacy state machine plus three review seams', () => {
    assert.match(workflowStart, /exploring.*specifying.*bridging.*approved-for-build.*executing.*closing/s);
    assert.match(specWriter, /proposal-specs/i);
    assert.match(specWriter, /design-tasks/i);
    assert.match(contractBuilder, /dp_3_result/i);
    assert.doesNotMatch(contractBuilder, /dp_3_contract_hash/i);
    assert.match(buildExecutor, /final Reviewer|final review/i);
    assert.match(releaseArchivist, /final Reviewer|final review/i);
    const skills = [workflowStart, specWriter, contractBuilder, buildExecutor, releaseArchivist].join('\n');
    assert.doesNotMatch(skills, /state next|state confirm|review begin|review cancel|candidate_graph|message_graph|handoff_attestation|orchestration_mode|managed-independent-review/i);
  });
});
