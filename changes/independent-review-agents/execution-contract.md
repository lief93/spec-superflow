# Execution Contract: Independent Review Agents

## Intent Lock

- **Change name**: `independent-review-agents`
- **Problem to solve**: Planning Design/Tasks and completed implementation need
  semantic review from a fixed context independent of the Primary that authored
  them, without adding another orchestration system.
- **In scope**: One visible Primary, one hidden read-only Reviewer, three exact
  full-workflow checkpoints, compact current-only Review CLI, minimal DP
  identity bindings, host/packed runtime tests, and documentation.
- **Out of scope**: Dev role, extra workflow states, host continuity protocol,
  review history service, Reviewer mutations, tests or workflow-command
  execution, command allowlist or dedicated SCM tool, non-full review
  checkpoints, public-network/internal-machine work, release or publication.

## Approved Behavior

- **Approved requirement summary**: Exact full workflow reviews current
  Proposal/Specs, then current Design/Tasks, then the frozen final candidate in
  one independent Reviewer context per stage. A stage starts fresh and reuses
  that context only for its one permitted repair/re-review. Primary owns all
  writes, tests, state, user questions, and fixes.
- **Key scenarios**: Safe current-result recording; unsafe transport rejection;
  DP-1/DP-2/DP-3 binding; explicit-base worktree staleness; `Request Changes`
  repair; final approval before the single closing transition; identical VS
  Code/OpenCode review topology.
- **Acceptance checks**: Named public-interface tests below, full `npm test`,
  version consistency, source doctor, artifact validate/state check, diff check,
  fresh package contents and packed runtime.

## Requirement Traceability

| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|
| Full workflow uses one Primary and one fixed independent Reviewer | Primary owns mutable work; the fixed Reviewer is hidden and behaviorally read-only while using ordinary project-read and terminal tools; each exact-full checkpoint starts fresh, receives only bounded metadata/path references, processes every return through raw write/record/check, and permits only one same-context repair/re-review; non-full routes remain unchanged. | Host contract tests prove topology, ordinary inspection-tool availability, no-mutation instructions, body-free handoff, durable return ordering, bounded stage-context reuse, and non-full isolation. | Batch 2 |
| Planning has two independent semantic checkpoints | Proposal/Specs review precedes DP-1 and Design/Tasks; Design/Tasks review precedes DP-2 and contract creation; overlap is checked before downstream repair and static selectors are not inferred from runtime calls. | Planning-order, ordered semantic-scan, and guard-binding tests reject merged, missing, overlapping, semantically invalid, or stale gates. | Batch 2 |
| Final review blocks closing without replacing mechanical gates | Final evidence freezes before review; `Approved` permits only the single guarded closing transition; `Request Changes` keeps executing. | Final-order and Review CLI repair tests prove both verdict paths. | Batch 3 |
| Review CLI records only current stage evidence | Only candidate/record/check exist; fixed safe inbox input atomically replaces one stage current result and stale or invalid evidence fails closed. | Review CLI public-interface tests cover safe modes, unsafe transports, exact schema, and unchanged state. | Batch 1 |
| Final candidate covers the complete worktree | Public output contains metadata and paths only; explicit base, porcelain status, complete tracked diff, every untracked byte, and evidence inputs define final identity internally. Reviewer independently reads SCM and each untracked file. | Candidate tests reject body leakage and mutate every input class and staged/unstaged state; OpenCode public-tool runtime performs the required reads and proves identity/status/cached diff remain unchanged. | Batch 1 |
| Existing state and decision-point flow remains authoritative | Existing state init/check/transition/get/rebuild/set flow advances all states; only three identity/hash bindings are added. | Full lifecycle state test and transition guard test prove existing commands and bindings. | Batch 1, Batch 2 |
| VS Code and OpenCode register the same review topology | Both hosts expose one Primary and one hidden fixed Reviewer while bootstrap remains isolated. | VS Code and OpenCode registration tests plus packed runtime resolution prove permissions and assets. | Batch 2, Batch 3 |

## AC Test Matrix

| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|---|---|
| Review CLI records only current stage evidence | Primary records a valid Reviewer result | Integration | Node.js 22 | Update | tests/lib/cmd-review.test.mjs | records and checks 0644 and 0600 fixed inbox reports atomically | A valid fixed report becomes the selected stage current result and remains checkable for both supported regular-file modes. |
| Review CLI records only current stage evidence | Review transport or result is unsafe | Integration | Node.js 22 | Update | tests/lib/cmd-review.test.mjs | rejects symlink, directory, path override, traversal, and wrong stage inboxes | Unsafe report transport exits nonzero before workflow state or current stage evidence changes. |
| Review CLI records only current stage evidence | Review transport or result is unsafe | Unit | Node.js 22 | Add | tests/lib/review-evidence.test.mjs | requires every finding line to be a positive integer | The result schema rejects null and every non-positive or non-integer line while accepting an exact positive line. |
| Final candidate covers the complete worktree | Final work changes after approval | Integration | Git and Node.js 22 | Update | tests/lib/worktree-review-candidate.test.mjs | final identity fails closed on semantic Git base and worktree drift | Any base, committed, staged, unstaged, or untracked drift invalidates the current final approval. |
| Final candidate covers the complete worktree | Reviewer inspects a frozen final candidate | Integration | Git and Node.js 22 | Add | tests/lib/review-candidate.test.mjs | keeps final candidate body-free while full tracked and untracked bytes bind identity | Primary handoff size does not scale with source bodies, and no tracked diff or untracked text leaks through public candidate JSON. |
| Final candidate covers the complete worktree | Reviewer inspects a frozen final candidate | Integration | Git and Node.js 22 | Add | tests/lib/worktree-review-candidate.test.mjs | collects changed gitlink metadata without reading the submodule directory as a file | A changed tracked gitlink produces mode/length/hash metadata and no submodule source body instead of treating its directory as an untracked file. |
| Final candidate covers the complete worktree | Reviewer inspects a frozen final candidate | Integration | Git and Node.js 22 | Add | tests/lib/worktree-review-candidate.test.mjs | binds gitlink pointer dirty and index-status changes into final identity | Submodule commit, dirty worktree, and staged-versus-unstaged status drift each invalidate the frozen final identity while public metadata remains body-free. |
| Final candidate covers the complete worktree | Reviewer inspects a frozen final candidate | Integration | OpenCode Plugin 1.14.48 | Update | tests/integration/opencode-runtime.test.mjs | resolves hidden Agent tools through pinned OpenCode for repository and packed Plugin contexts | The declared Reviewer identity can obtain status/diff/log/show and untracked content through public host tools while candidate identity, porcelain status, and cached diff remain unchanged. |
| Existing state and decision-point flow remains authoritative | Planning advances through the existing state machine | Integration | Node.js 22 | Update | tests/lib/cmd-state.test.mjs | progresses a new full-workflow Change through every mainline state | Existing init, guard, transition, set, and get commands remain sufficient for the complete full-workflow lifecycle. |
| Full workflow uses one Primary and one fixed independent Reviewer | Primary requests an independent semantic review | Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | keeps one visible Primary and one fixed read-only Reviewer | The authoring context and semantic review context are distinct; Reviewer uses ordinary inspection tools but is contractually prohibited from mutation or delegation. |
| Full workflow uses one Primary and one fixed independent Reviewer | Primary requests an independent semantic review | Integration | VS Code and OpenCode Plugin contract | Add | tests/lib/managed-review-workflow.test.mjs | hands Reviewer a bounded path index instead of inline artifact copies | The independent context resolves current artifact and evidence references without receiving a copied prompt-sized artifact body. |
| Full workflow uses one Primary and one fixed independent Reviewer | Primary requests an independent semantic review | Integration | VS Code and OpenCode Plugin contract | Add | tests/lib/managed-review-workflow.test.mjs | makes raw -> record -> check the only legal return sequence | Primary cannot interpret or repair before the exact Reviewer result is durably recorded and checked. |
| Full workflow uses one Primary and one fixed independent Reviewer | Non-full workflow continues | Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | keeps hotfix/tweak and ordinary runtime behavior outside review/bootstrap | Non-full workflows do not create Review evidence and ordinary requests do not invoke bootstrap MCP. |
| Planning has two independent semantic checkpoints | Proposal and Specs become ready for DP-1 | Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | separates the two Planning reviews from user DP-1/DP-2 and contract DP-3 | Proposal and Specs require current independent approval before user-bound DP-1 and before downstream artifacts. |
| Planning has two independent semantic checkpoints | Proposal and Specs become ready for DP-1 | Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | closes Proposal and Specs against intent before first review | Primary detects overlapping or incomplete Scenarios before freezing the first Planning candidate. |
| Planning has two independent semantic checkpoints | Design and Tasks become ready for DP-2 | Integration | Node.js 22 | Update | tests/lib/guard-transitions.test.mjs | binds DP-2 to the current Design review for exact full workflow | Stale Design/Tasks approval or its DP-2 binding fails the independent-review guard for exact full workflow. |
| Planning has two independent semantic checkpoints | Design and Tasks become ready for DP-2 | Integration | VS Code and OpenCode Plugin contract | Add | tests/lib/managed-review-workflow.test.mjs | runs overlap preflight before the fixed Design and Tasks scan | Upstream overlap fails closed before downstream repair, and static Android selectors are not inferred from runtime calls. |
| VS Code and OpenCode register the same review topology | Plugin host resolves review capabilities | Integration | VS Code Agent Plugin | Update | tests/lib/vscode-agent-plugin.test.mjs | exposes one visible Primary and one hidden fixed Reviewer | VS Code exposes the intended two contexts and does not add a Dev Agent. |
| VS Code and OpenCode register the same review topology | Plugin host resolves review capabilities | Integration | OpenCode Plugin 1.14.48 | Update | tests/lib/opencode-plugin.test.mjs | registers one Primary, one bootstrap-only setup worker, and one behavior-read-only Reviewer | OpenCode isolates setup and Reviewer behavior while Primary can invoke only the fixed Reviewer. |
| Final review blocks closing without replacing mechanical gates | Final candidate is approved | Integration | VS Code and OpenCode Plugin contract | Update | tests/lib/managed-review-workflow.test.mjs | keeps final semantic review after mechanics and before the single closing transition | Current final approval is the last semantic gate and closing remains owned by release-archivist exactly once. |
| Final review blocks closing without replacing mechanical gates | Final candidate requests changes | Integration | Node.js 22 | Update | tests/lib/cmd-review.test.mjs | keeps workflow state unchanged on Request Changes and allows repair re-review | A blocking verdict cannot advance state, and repaired current content receives a distinct fresh review candidate. |

## Design Constraints

- **Project baseline source**: Existing Spec Superflow CLI, guards, Skills, VS
  Code Agent Plugin, OpenCode Plugin, and npm packaging conventions.
- **Selected classic implementations**: Existing command dispatcher, state
  loader/set fields, transition dimension checks, Markdown Agent/Skill assets,
  temporary-repository integration fixtures, and atomic file replacement.
- **Approved deviations**: None.
- **Project Memory source**: Not configured.
- **Technology constraints**: Node.js ESM with built-in modules only; no new
  runtime dependency or network access.
- **Architecture constraints**: One Primary owns mutation; one fixed Reviewer
  owns semantic judgment and uses ordinary host tools only for read-only
  inspection; existing state machine remains authoritative.
- **Data and interface constraints**: Fixed change-local JSON report paths,
  exact schemas and stages, project-relative finding paths, deterministic
  candidate identities, no caller-selected report input.
- **Dependency constraints**: Review evidence builds on current artifact/Git
  collectors; guards consume Review check output; hosts consume CLI and Skills.
- **Reuse targets and extension points**: state loader, hash utilities, guard
  dimension runner, Plugin registration, package/runtime fixtures.
- **Runtime and platform facts**: Static/Node tests prove checked source
  behavior; OpenCode 1.14.48 public debug interfaces prove required Reviewer
  SCM/file reads without candidate mutation in source and packed contexts.
  Unexecuted real VS Code Chat, full model-driven OpenCode business workflow,
  and company-internal validation remain `PENDING`.

## Task Batches

### Batch 1

- **Goal**: Implement compact safe current Review evidence on the existing CLI
  and state machine.
- **Inputs**: Existing state commands, hash utilities, guards, Git worktree.
- **Outputs**: Review candidate/record/check, candidate collectors, current
  evidence validator, minimal DP bindings, public CLI tests.
- **Done when**: Safe positive paths pass; every unsafe/stale path exits nonzero;
  existing full mainline state lifecycle still passes.

### Batch 2

- **Goal**: Register the fixed Reviewer and enforce the two Planning checkpoints
  in VS Code, OpenCode, and shared Skills.
- **Inputs**: Batch 1 Review CLI and current identity checks.
- **Outputs**: Host prompts/tool contracts, review-only full routing, DP-1/DP-2
  binding, shared Skill boundaries, host contract tests.
- **Done when**: Both hosts expose the same topology; exact full Planning order
  is fail-closed; non-full and bootstrap boundaries do not regress.

### Batch 3

- **Goal**: Complete final review/closing behavior, packed runtime proof,
  current docs, and honest evidence.
- **Inputs**: Batch 1 and Batch 2 runtime and host contracts.
- **Outputs**: Final review guard, state-only closing route, packed runtime test,
  package hygiene, updated artifacts/docs/evidence.
- **Done when**: Targeted/full tests and all quality gates pass; package contains
  required runtime only; real unexecuted environments remain `PENDING`.

## Test Obligations

- **Behavior that must start with a failing test**: Review command surface and
  report safety; candidate staleness; DP identity guards; host topology;
  final-review transition order; packed runtime commands.
- **Required edge cases**: 0600/0644 regular files, symlink, directory, path
  override, traversal, wrong stage, malformed/forbidden result, `Request
  Changes`, stale Planning, mismatched explicit final base, each Git worktree
  layer, non-full route, missing real runtime evidence.
- **Regression-sensitive areas**: state lifecycle, `/workflow-init`, ordinary
  request bootstrap isolation, project-init, version consistency, doctor,
  package entry hygiene, source/packed command parity.

## Frontend Verification

- **Frontend Impact**: No
- **Reason**: This change configures AI Agent prompts, CLI evidence, and guards;
  it does not alter an application UI. Real host behavior is a runtime evidence
  item and remains separate from UI product testing.

## Execution Mode

- **Mode**: SDD
- **Selection rationale**: The change spans CLI, state/guards, two Plugin hosts,
  shared Skills, package runtime, tests, and documentation. Batches preserve
  dependency order while Primary performs the work directly.

## Verification Dimensions

| Dimension | Status | Findings |
|---|---|---|
| Completeness | Pending | Final full-suite and package evidence must be refreshed after all synchronization. |
| Correctness | Pending | Fixed independent Reviewer must assess the frozen candidate. |
| Coherence | Pending | Final artifact validation and state hash check must pass. |

**Overall conclusion**: Pending fixed Reviewer result.

## Review Gates

- **Mandatory review points**: Current `proposal-specs` before DP-1/Design;
  current `design-tasks` before DP-2/contract; current explicit-base `final`
  before closing.
- **Blocking categories**: Critical/High/Medium semantic Findings; unavailable
  Reviewer; malformed/unsafe result; `Request Changes`; stale candidate;
  failing mechanical guard; missing user DP binding.

## Escalation Rules

- **When to return to `specifying`**: Approved intent, Proposal, Specs, Design,
  or Tasks meaning must change.
- **When to return to `bridging`**: Execution contract no longer matches current
  approved Planning artifacts or implementation constraints.
- **When implementation must not continue**: Any current required review,
  user DP, contract hash, transition guard, named test, or scope fence fails.
