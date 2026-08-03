# Tasks: Independent Review Agents

## Interfaces

- Batch 1 produces the compact Review CLI, candidate identity, current-result
  validation, and minimal DP bindings consumed by later guards and hosts.
- Batch 2 consumes Batch 1 and produces the shared Skill and VS Code/OpenCode
  two-Agent topology with the two Planning checkpoints.
- Batch 3 consumes both earlier Batches and produces final review/closing
  behavior, package/runtime regression coverage, documentation, and evidence.

## Batch 1: Current review evidence on the existing state machine

Depends on: None

### AC: Primary records a valid Reviewer result

- **Requirement**: Review CLI records only current stage evidence
- **User-visible**: No

#### File Changes

##### Create `scripts/lib/cmd-review.mjs`

- **Change**: Implement only `candidate`, `record`, and `check`; use fixed stage
  inbox/current paths and atomic current-result replacement.

##### Create `scripts/lib/review-evidence.mjs`

- **Change**: Validate exact result schema, typed verdict, allowed finding
  paths, and current candidate identity.

##### Modify `scripts/spec-superflow.mjs`

- **Change**: Register the compact `review` command family without changing the
  existing state command family.

##### Create `tests/lib/cmd-review.test.mjs`

- **Change**: Exercise fixed-path record/check behavior and file-mode support
  through the public CLI.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js 22 | Update | tests/lib/cmd-review.test.mjs | records and checks 0644 and 0600 fixed inbox reports atomically | A valid fixed report becomes the selected stage current result and remains checkable for both supported regular-file modes. |

#### TDD Steps

- [x] RED: Run the named CLI test and observe missing fixed-path record/check behavior.
- [x] GREEN: Implement the minimum schema validation and atomic replacement needed for the test.
- [x] REFACTOR: Run all Review CLI and evidence tests.

### AC: Review transport or result is unsafe

- **Requirement**: Review CLI records only current stage evidence
- **User-visible**: No

#### File Changes

##### Modify `scripts/lib/cmd-review.mjs`

- **Change**: Reject report path overrides, traversal, symlink, directory,
  wrong-stage, and outside-Change transport before reading or replacing current
  evidence.

##### Modify `scripts/lib/review-evidence.mjs`

- **Change**: Reject malformed verdicts, forbidden fields, invalid finding
  targets or non-positive-integer lines, and stage/identity mismatches.

##### Modify `tests/lib/cmd-review.test.mjs`

- **Change**: Add public CLI negatives for every unsafe transport category.

##### Create `tests/lib/review-evidence.test.mjs`

- **Change**: Prove Finding lines reject null, zero, negative, fractional, and
  string values while accepting a positive integer.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js 22 | Update | tests/lib/cmd-review.test.mjs | rejects symlink, directory, path override, traversal, and wrong stage inboxes | Unsafe report transport exits nonzero before workflow state or current stage evidence changes. |
| Unit | Node.js 22 | Add | tests/lib/review-evidence.test.mjs | requires every finding line to be a positive integer | The result schema rejects null and every non-positive or non-integer line while accepting an exact positive line. |

#### TDD Steps

- [x] RED: Run the named negatives and observe at least one unsafe transport accepted.
- [x] GREEN: Add containment, real-file, fixed-name, and stage checks.
- [x] REFACTOR: Run Review CLI and filesystem-boundary regressions.

### AC: Final work changes after approval

- **Requirement**: Final candidate covers the complete worktree
- **User-visible**: No

#### File Changes

##### Create `scripts/lib/worktree-review-candidate.mjs`

- **Change**: Collect explicit Git base plus committed, staged, unstaged, and
  untracked work without writing candidate artifacts.

##### Create `scripts/lib/review-candidate.mjs`

- **Change**: Hash stage targets and final evidence into deterministic candidate
  identities and recompute them during check.

##### Create `tests/lib/worktree-review-candidate.test.mjs`

- **Change**: Prove semantic base and every worktree layer affect final identity.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Git and Node.js 22 | Update | tests/lib/worktree-review-candidate.test.mjs | final identity fails closed on semantic Git base and worktree drift | Any base, committed, staged, unstaged, or untracked drift invalidates the current final approval. |

#### TDD Steps

- [x] RED: Run the final identity test and observe an unrepresented Git layer remain current.
- [x] GREEN: Include the missing layer and explicit base in canonical identity.
- [x] REFACTOR: Run candidate, evidence, CLI, and guard regressions.

### AC: Reviewer inspects a frozen final candidate

- **Requirement**: Final candidate covers the complete worktree
- **User-visible**: No

#### File Changes

##### Modify `scripts/lib/worktree-review-candidate.mjs`

- **Change**: Keep full tracked diff and raw untracked bytes internal to framed
  identity computation, including porcelain-v2 staged/unstaged state. Recognize
  tracked gitlink mode `160000`, derive body-free metadata from its Git object
  and current commit id, and frame that id without reading the directory.

##### Modify `scripts/lib/review-candidate.mjs`

- **Change**: Publish only fixed-base identity, changed-file metadata, review
  targets, and allowed Finding paths; never publish tracked diff or untracked
  source text.

##### Modify `agents/spec-superflow-reviewer.agent.md`

- **Change**: Require Reviewer-owned read-only status/diff/log/show and complete
  changed/untracked inspection through ordinary host tools while prohibiting
  mutation, tests, workflow commands, MCP, and nested Agents.

##### Modify `tests/lib/review-candidate.test.mjs`

- **Change**: Prove large tracked/untracked bodies never enter public JSON,
  equal-length byte changes alter identity without scaling output, and moving
  unchanged bytes from unstaged to staged invalidates identity.

##### Modify `tests/lib/worktree-review-candidate.test.mjs`

- **Change**: Build a pure temporary local submodule fixture that proves changed
  gitlink collection does not read a directory as a file, exposes no submodule
  body, and invalidates identity on pointer, dirty, and staged-status changes.

##### Modify `tests/integration/opencode-runtime.test.mjs`

- **Change**: Through OpenCode 1.14.48 public Agent tool interfaces, execute the
  required Reviewer Git/file reads and compare worktree identity, porcelain
  status, and cached diff before and after.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Git and Node.js 22 | Add | tests/lib/review-candidate.test.mjs | keeps final candidate body-free while full tracked and untracked bytes bind identity | Primary handoff size does not scale with source bodies, and no tracked diff or untracked text leaks through public candidate JSON. |
| Integration | Git and Node.js 22 | Add | tests/lib/worktree-review-candidate.test.mjs | collects changed gitlink metadata without reading the submodule directory as a file | A changed tracked gitlink produces mode/length/hash metadata and no submodule source body instead of treating its directory as an untracked file. |
| Integration | Git and Node.js 22 | Add | tests/lib/worktree-review-candidate.test.mjs | binds gitlink pointer dirty and index-status changes into final identity | Submodule commit, dirty worktree, and staged-versus-unstaged status drift each invalidate the frozen final identity while public metadata remains body-free. |
| Integration | OpenCode Plugin 1.14.48 | Update | tests/integration/opencode-runtime.test.mjs | resolves hidden Agent tools through pinned OpenCode for repository and packed Plugin contexts | The declared Reviewer identity can obtain status/diff/log/show and untracked content through public host tools while candidate identity, porcelain status, and cached diff remain unchanged. |

#### TDD Steps

- [x] RED: Observe public candidate JSON contain raw diff/untracked bodies and unchanged bytes moving from unstaged to staged retain identity.
- [x] GREEN: Publish metadata only, frame status/diff/untracked bytes internally, and require Reviewer-owned SCM/file inspection.
- [x] RED: Reproduce a changed tracked gitlink failing because its submodule directory is read as an untracked regular file.
- [x] GREEN: Recognize mode `160000`, frame its current commit id, and keep source bodies out of public metadata.
- [x] REFACTOR: Run candidate, host-contract, worktree, and public OpenCode runtime tests.

### AC: Planning advances through the existing state machine

- **Requirement**: Existing state and decision-point flow remains authoritative
- **User-visible**: No

#### File Changes

##### Modify `scripts/lib/state-loader.mjs`

- **Change**: Add only DP-1/DP-2 candidate identities as settable persisted
  bindings; preserve existing states, commands, and contract hash.

##### Modify `scripts/guard/guard.mjs`

- **Change**: Schedule the independent-review check without moving current
  review identity into the existing user-decision gate.

##### Modify `tests/lib/cmd-state.test.mjs`

- **Change**: Exercise the complete existing mainline transition flow and the
  minimum new bindings through public state commands.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js 22 | Update | tests/lib/cmd-state.test.mjs | progresses a new full-workflow Change through every mainline state | Existing init, guard, transition, set, and get commands remain sufficient for the complete full-workflow lifecycle. |

#### TDD Steps

- [x] RED: Run the mainline lifecycle test against the overextended command protocol and observe failure.
- [x] GREEN: Restore existing state commands and add only current identity bindings.
- [x] REFACTOR: Run state, guard, validate, and packaged CLI regressions.

## Batch 2: Fixed Reviewer and Planning checkpoints in both hosts

Depends on: Batch 1

### AC: Primary requests an independent semantic review

- **Requirement**: Full workflow uses one Primary and one fixed independent Reviewer
- **User-visible**: No

#### File Changes

##### Modify `agents/spec-superflow.agent.md`

- **Change**: Make Primary the only visible mutable context and define the
  short reference-only candidate handoff plus mandatory raw-write to
  record/check return sequence.

##### Create `agents/spec-superflow-reviewer.agent.md`

- **Change**: Define hidden behaviorally read-only semantic review with ordinary
  host project-read and terminal tools, required read-only SCM inspection,
  strict typed JSON output, overlap-first ordered Planning scans, honest static
  versus runtime proof, and explicit prohibition of mutations, tests, workflow
  commands, MCP, and nested Agents.

##### Modify `skills/workflow-start/SKILL.md`

- **Change**: Require every fixed Reviewer return to complete raw write,
  `review record`, and `review check` before interpretation, repair, another
  review, or state progression.

##### Create `tests/lib/managed-review-workflow.test.mjs`

- **Change**: Assert the two-Agent topology and the three review seams without
  relying on a host continuity protocol.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | keeps one visible Primary and one fixed read-only Reviewer | The authoring context and semantic review context are distinct; Reviewer uses ordinary inspection tools but is contractually prohibited from mutation or delegation. |
| Integration | VS Code and OpenCode Plugin contract | Add | tests/lib/managed-review-workflow.test.mjs | hands Reviewer a bounded path index instead of inline artifact copies | The independent context resolves current artifact and evidence references without receiving a copied prompt-sized artifact body. |
| Integration | VS Code and OpenCode Plugin contract | Add | tests/lib/managed-review-workflow.test.mjs | makes raw -> record -> check the only legal return sequence | Primary cannot interpret or repair before the exact Reviewer result is durably recorded and checked. |

#### TDD Steps

- [x] RED: Run the topology test and observe the missing or overextended role boundary.
- [x] GREEN: Register only Primary and fixed Reviewer with the required host tools and behavioral boundary.
- [x] REFACTOR: Run all host contract tests.

### AC: Non-full workflow continues

- **Requirement**: Full workflow uses one Primary and one fixed independent Reviewer
- **User-visible**: No

#### File Changes

##### Modify `skills/workflow-start/SKILL.md`

- **Change**: Enable fixed Reviewer checkpoints only for exact full and retain
  existing `hotfix` and `tweak` routes.

##### Modify `skills/build-executor/SKILL.md`

- **Change**: Keep Primary as the implementation context for full while leaving
  non-full direct paths free of fixed Reviewer checkpoints.

##### Modify `tests/lib/managed-review-workflow.test.mjs`

- **Change**: Assert non-full and ordinary runtime remain outside review and bootstrap.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | keeps hotfix/tweak and ordinary runtime behavior outside review/bootstrap | Non-full workflows do not create Review evidence and ordinary requests do not invoke bootstrap MCP. |

#### TDD Steps

- [x] RED: Run the route-boundary test and observe old full-only policy leaking into ordinary or non-full work.
- [x] GREEN: Restrict review seams to exact full and preserve the existing fast paths.
- [x] REFACTOR: Run shared Skill and bootstrap regressions.

### AC: Proposal and Specs become ready for DP-1

- **Requirement**: Planning has two independent semantic checkpoints
- **User-visible**: No

#### File Changes

##### Modify `skills/spec-writer/SKILL.md`

- **Change**: Bound the first full Planning stage to intent, Proposal, and
  Specs; compare Scenario trigger, outcome, observable surface, risk, and
  subset/superset before review; require current review before user DP-1 and
  before Design/Tasks.

##### Modify `skills/need-explorer/SKILL.md`

- **Change**: Return clarified intent to Primary without writing artifacts or
  recording DP-1 for exact full.

##### Modify `tests/lib/managed-review-workflow.test.mjs`

- **Change**: Assert the first semantic checkpoint remains separate from DP-1.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | separates the two Planning reviews from user DP-1/DP-2 and contract DP-3 | Proposal and Specs require current independent approval before user-bound DP-1 and before downstream artifacts. |
| Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | closes Proposal and Specs against intent before first review | Primary detects overlapping or incomplete Scenarios before freezing the first Planning candidate. |

#### TDD Steps

- [x] RED: Run the Planning-order test and observe artifact or decision gates merged.
- [x] GREEN: Split Proposal/Specs review, user DP-1, and downstream authoring.
- [x] REFACTOR: Run Planning Skill and guard regressions.

### AC: Design and Tasks become ready for DP-2

- **Requirement**: Planning has two independent semantic checkpoints
- **User-visible**: No

#### File Changes

##### Modify `skills/spec-writer/SKILL.md`

- **Change**: Bound the second stage to Design and Tasks and treat approved
  upstream artifacts as read-only; distinguish static source obligations from
  runtime proof with an explicit Android quantity-selector counterexample.

##### Modify `skills/contract-builder/SKILL.md`

- **Change**: Keep DP-2 and DP-3 separate and bind user DP-3 to the current
  generated contract hash.

##### Modify `scripts/guard/guard.mjs`

- **Change**: Require current Design/Tasks approval and DP bindings at the
  existing `specifying` to `bridging` transition.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js 22 | Update | tests/lib/guard-transitions.test.mjs | binds DP-2 to the current Design review for exact full workflow | Stale Design/Tasks approval or its DP-2 binding fails the independent-review guard for exact full workflow. |
| Integration | VS Code and OpenCode Plugin contract | Add | tests/lib/managed-review-workflow.test.mjs | runs overlap preflight before the fixed Design and Tasks scan | Upstream overlap fails closed before downstream repair, and static Android selectors are not inferred from runtime calls. |

#### TDD Steps

- [x] RED: Run the binding test and observe an unbound or stale decision accepted.
- [x] GREEN: Compare persisted bindings with current review and contract identity.
- [x] REFACTOR: Run Review CLI, state, and all transition guards.

### AC: Plugin host resolves review capabilities

- **Requirement**: VS Code and OpenCode register the same review topology
- **User-visible**: No

#### File Changes

##### Modify `.opencode/plugins/spec-superflow.js`

- **Change**: Keep the Plugin a pure registration layer for Primary, setup, and
  hidden fixed Reviewer without planning write hooks.

##### Create `.opencode/agents/spec-superflow-reviewer.md`

- **Change**: Adapt the read-only semantic Reviewer contract to a fresh initial
  stage task and one same-context re-review.

##### Create `tests/integration/opencode-runtime.test.mjs`

- **Change**: Resolve repository and freshly packed prompts through pinned
  public `opencode debug agent/config` and assert the short handoff, ordered
  return chain, overlap-first scan, and Android static-selector boundary.

##### Modify `tests/lib/vscode-agent-plugin.test.mjs`

- **Change**: Verify the VS Code manifest, Agent permissions, bootstrap boundary,
  and Planning/final checkpoint order.

##### Create `tests/lib/opencode-plugin.test.mjs`

- **Change**: Verify resolved OpenCode registration and permission topology.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | VS Code Agent Plugin | Update | tests/lib/vscode-agent-plugin.test.mjs | exposes one visible Primary and one hidden fixed Reviewer | VS Code exposes the intended two contexts and does not add a Dev Agent. |
| Integration | OpenCode Plugin 1.14.48 | Update | tests/lib/opencode-plugin.test.mjs | registers one Primary, one bootstrap-only setup worker, and one behavior-read-only Reviewer | OpenCode isolates setup and Reviewer behavior while Primary can invoke only the fixed Reviewer. |

#### TDD Steps

- [x] RED: Run both host topology tests and observe inconsistent registration or permissions.
- [x] GREEN: Align host Agent definitions and keep the central adapter registration-only.
- [x] REFACTOR: Resolve repository and packed OpenCode configurations and rerun host tests.

## Batch 3: Final review, package runtime, and delivery evidence

Depends on: Batch 2

### AC: Final candidate is approved

- **Requirement**: Final review blocks closing without replacing mechanical gates
- **User-visible**: No

#### File Changes

##### Modify `skills/release-archivist/SKILL.md`

- **Change**: Split full closure into pre-review evidence freeze and post-approval
  state-only transition; keep unexecuted real runtime honestly `PENDING`.

##### Modify `scripts/guard/checks/review-approved.mjs`

- **Change**: Require current final approval only on the existing executing to
  closing guard.

##### Modify `tests/lib/managed-review-workflow.test.mjs`

- **Change**: Assert final review follows mechanical freeze and precedes the
  single closing transition.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | keeps final semantic review after mechanics and before the single closing transition | Current final approval is the last semantic gate and closing remains owned by release-archivist exactly once. |

#### TDD Steps

- [x] RED: Run the closing-order test and observe review or transition ownership misplaced.
- [x] GREEN: Freeze evidence before review and allow only the post-approval state transition.
- [x] REFACTOR: Run lifecycle and closing guard regressions.

### AC: Final candidate requests changes

- **Requirement**: Final review blocks closing without replacing mechanical gates
- **User-visible**: No

#### File Changes

##### Modify `skills/build-executor/SKILL.md`

- **Change**: Route final findings back to Primary for bounded TDD repair and a
  complete fresh evidence freeze.

##### Modify `skills/code-reviewer/SKILL.md`

- **Change**: Reserve fixed semantic code review for the final full-workflow
  checkpoint rather than per-AC or per-Batch review.

##### Modify `tests/lib/cmd-review.test.mjs`

- **Change**: Prove `Request Changes` leaves state unchanged and a changed
  candidate can be reviewed afresh.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js 22 | Update | tests/lib/cmd-review.test.mjs | keeps workflow state unchanged on Request Changes and allows repair re-review | A blocking verdict cannot advance state, and repaired current content receives a distinct fresh review candidate. |

#### TDD Steps

- [x] RED: Run the repair test and observe a blocking verdict mutate state or prevent a valid fresh review.
- [x] GREEN: Keep review evidence independent from state progression and recompute current identity.
- [x] REFACTOR: Run final candidate, record/check, and closing guard tests.
