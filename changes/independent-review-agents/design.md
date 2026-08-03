# Design: Independent Review Agents

## Context

Spec Superflow already has a user-visible Primary, a persisted state machine,
guarded transitions, DP fields, shared Skills, VS Code Plugin assets, and an
OpenCode adapter. The change needs independent semantic judgment at the two
Planning boundaries and final implementation boundary. It must not create a
parallel manager/developer protocol or depend on host-specific continuity.

Mechanical tests, validation, package checks, workflow commands, and runtime
probes remain Primary responsibilities. Reviewer uses ordinary host
project-read and terminal tools to run the read-only `review candidate` command,
inspect the frozen repository, and run read-only SCM commands. Primary supplies
only the Change directory and stage. A review result is useful only while its
candidate identity remains current.

## Goals

- One visible Primary owns every mutable action and user interaction.
- One hidden fixed Reviewer receives one fresh independent context for each
  stage's initial review, may reuse it only for that stage's one re-review, and
  is behaviorally read-only while retaining ordinary host tools needed to
  inspect current SCM state.
- Exact full workflow has two Planning checkpoints and one final checkpoint.
- Review approval, mechanical gates, and user DP confirmation remain distinct.
- Review evidence is small, deterministic, safe to record, and stale when any
  relevant candidate input changes.
- Existing state transitions, `hotfix`/`tweak`, bootstrap, package, and project
  initialization behavior remain intact.

## Non-goals

- No additional Agent role, workflow state, lock, receipt, review history, or
  host continuity model.
- No Reviewer edits, mutating Git commands, tests, workflow execution other
  than read-only `review candidate`, state changes, user contact, nested Agent
  calls, custom command allowlist, or
  dedicated read-only SCM tool.
- No public-network or company-internal runtime work.

## Project Baseline Alignment

| Area | Existing Baseline | Reuse |
|---|---|---|
| Workflow state | `scripts/lib/cmd-state.mjs`, `scripts/guard/guard.mjs` | Keep `state init/check/transition/get/rebuild/set`; add only review evidence checks and DP identity fields |
| CLI commands | `scripts/spec-superflow.mjs` command dispatcher | Register one compact `review` family with three subcommands |
| Host registration | VS Code Agent Markdown and `.opencode/plugins/spec-superflow.js` | Register the same Primary/Reviewer topology in each host; keep setup isolated and express Reviewer immutability as a behavioral contract |
| Skills | Existing state-routed shared Skills | Add three review seams without changing state names or non-full routes |
| Evidence | Change-local Markdown plus `.spec-superflow.yaml` hashes | Keep fixed report paths under `<change-dir>/reviews/` and current-only results |
| Packaging | Existing npm files and packed runtime test | Include production runtime and prompts; exclude tests/Changes from the archive |

## Requirement And Scenario Coverage

| Requirement | Scenario | Design Decision | Affected Area | Why Here |
|---|---|---|---|---|
| Full workflow uses one Primary and one fixed independent Reviewer | Primary requests an independent semantic review | Fixed two-Agent host topology | `agents/`, `.opencode/agents/`, `.opencode/plugins/spec-superflow.js` | Independent context plus Plugin-normalized Change-and-stage invocation creates the review boundary while preserving Reviewer-owned inspection |
| Full workflow uses one Primary and one fixed independent Reviewer | Non-full workflow continues | Three seams on the existing workflow | `skills/workflow-start/SKILL.md`, shared phase Skills | Routing can restrict checkpoints to exact full while retaining fast paths |
| Planning has two independent semantic checkpoints | Proposal and Specs become ready for DP-1 | Planning approval binds current candidate identity | Primary prompts, `scripts/guard/checks/review-approved.mjs` | DP-1 must prove it confirms the reviewed Proposal/Specs candidate |
| Planning has two independent semantic checkpoints | Design and Tasks become ready for DP-2 | Planning approval binds current candidate identity | Primary prompts, Planning Skills, transition guard | Contract creation must wait for current Design/Tasks review and DP-2 |
| Final review blocks closing without replacing mechanical gates | Final candidate is approved | Final freeze uses the Change-owned execution base | State CLI, review candidate collector, release Skill, closing guard | Closing must cover all work since this Change first entered execution and happen once |
| Final review blocks closing without replacing mechanical gates | Final candidate requests changes | Current-only review evidence | Review CLI and Primary repair loop | A changed candidate invalidates approval without changing workflow state |
| Review CLI records only current stage evidence | Primary records a valid Reviewer result | Fixed safe report transport | `scripts/lib/cmd-review.mjs`, `scripts/lib/review-evidence.mjs` | Fixed inbox and atomic current replacement avoid caller-selected paths |
| Review CLI records only current stage evidence | Review transport or result is unsafe | Fixed safe report transport | Review CLI validation and tests | Unsafe path/file/schema inputs must fail before any current result changes |
| Final candidate covers the complete worktree | Change enters execution | Final freeze uses the Change-owned execution base | `scripts/lib/cmd-state.mjs`, `scripts/lib/state-loader.mjs`, Review CLI | Each Change captures its own first executing commit without requiring a clean or separate worktree |
| Final candidate covers the complete worktree | Final work changes after approval | Final freeze uses the Change-owned execution base | `scripts/lib/cmd-state.mjs`, `scripts/lib/worktree-review-candidate.mjs`, `scripts/lib/review-candidate.mjs` | Committed and uncommitted inputs since first execution must participate in staleness without Primary-prepared review content |
| Final candidate covers the complete worktree | Reviewer discovers and inspects a frozen final candidate | Fixed two-Agent host topology | `scripts/lib/worktree-review-candidate.mjs`, `scripts/lib/review-candidate.mjs`, Reviewer prompts | Reviewer independently acquires the complete SCM/file view and identity detects later drift |
| Existing state and decision-point flow remains authoritative | Planning advances through the existing state machine | Three seams on the existing workflow | state loader, DP guard, workflow Skills | Review is an added gate, not another transition model |
| VS Code and OpenCode register the same review topology | Plugin host resolves review capabilities | Fixed two-Agent host topology | VS Code/OpenCode prompts, manifests, runtime tests | Both supported hosts need the same visible/hidden role and behavioral read-only boundary |

## Decisions

### Decision: Fixed two-Agent host topology

- **Choice**: Keep the existing user-visible `Spec Superflow` Primary and add one
  hidden `Spec Superflow Reviewer`. Primary may invoke only that Reviewer for
  semantic review. Reviewer uses ordinary project-read and terminal tools but
  is instructed not to edit, stage, commit, push, checkout, reset, clean, run
  tests or workflow commands other than read-only `review candidate`, change
  state, or invoke another Agent. OpenCode reduces each Reviewer task to the
  exact Change directory and stage. Reviewer discovers current artifacts,
  repository evidence, and Git scope itself. Every return is durably processed
  as raw write, record, then check before Primary acts.
- **Rationale**: This supplies a genuinely independent context while leaving all
  mutable work and user coordination with one Agent.
- **Alternatives considered**: A Manager/Dev/Reviewer trio was rejected because
  it adds a role and coordination surface. Primary self-review was rejected
  because it does not provide independent context.

### Decision: Three seams on the existing workflow

- **Choice**: Exact `workflow: full` uses `proposal-specs`, `design-tasks`, and
  `final`. No review checkpoint runs for `hotfix` or `tweak`. Existing guarded
  state transitions remain the only workflow progression mechanism.
- **Rationale**: These are the points where semantic defects become expensive:
  before technical design, before the execution contract, and before closing.
- **Alternatives considered**: Review every artifact or every Batch was rejected
  as high latency and duplicative. A new review state machine was rejected as
  unnecessary.

### Decision: Planning approval binds current candidate identity

- **Choice**: After current Reviewer `Approved`, Primary asks the user for DP-1
  or DP-2 and records both the user decision and the exact reviewed candidate
  identity. Before Proposal/Specs approval, Reviewer scans Scenario overlap by
  trigger, outcome, observable surface, risk, and subset/superset. Before
  Design/Tasks approval it performs overlap preflight first, fails closed for
  upstream conflict, then distinguishes static source obligations from runtime
  proof. DP-3 remains a separate user approval bound to current contract hash.
- **Rationale**: Reviewer approval cannot substitute for a product decision,
  and an old user decision cannot approve later changed artifacts.
- **Alternatives considered**: Reviewer auto-approval of DPs and unbound DP text
  were rejected because neither proves user intent applies to current content.

### Decision: Fixed safe report transport

- **Choice**: Reviewer returns one unfenced JSON object. Primary's first action
  writes it unchanged to `reviews/<stage>-pending-report.json`, immediately runs
  `review record`, and then runs `review check` before interpreting or editing.
  `review record` accepts no path override, validates real regular-file
  containment and schema, then atomically replaces
  `reviews/<stage>-current.json`. `review check` recomputes current identity.
- **Rationale**: A fixed in-change path is simple to explain and test. Atomic
  current replacement preserves one authoritative result per stage.
- **Alternatives considered**: Arbitrary report paths, result history, or a
  service were rejected as unnecessary and unsafe.

### Decision: Final freeze uses the Change-owned execution base

- **Choice**: On the first transition into `executing`, the state CLI records
  the resolved `HEAD` as immutable `execution_base_commit`. Later entries into
  `executing`, including from `debugging`, preserve it, and each Change owns its
  own value. Final candidate, record, and check default to that commit; an
  explicit `--base <review-base>` remains a diagnostic or compatibility
  override. Public JSON
  exposes the resolved base, worktree identity, changed-file status/path/from,
  mode, byte length, content hash, review targets, and finding allowlist, but no
  tracked diff or untracked source text. Reviewer independently runs `git
  status`, fixed-base `git diff`, `git log`, and necessary `git show`, then
  reads every untracked file. Internally, candidate identity frames the
  resolved base, porcelain-v2 status, complete base-to-worktree diff, every
  untracked byte, and final evidence inputs. A mixed worktree remains permitted
  because its exact state is identity-bound rather than hidden by a new
  worktree requirement.
- **Rationale**: Final review must cover the exact deliverable, including work
  that is not committed yet, without placing repository bodies in the public
  candidate. Status framing also detects an unchanged byte sequence moving
  between unstaged and staged state.
- **Alternatives considered**: Bare `git diff` was rejected because it misses
  untracked work and has ambiguous staging semantics. Requiring a
  Primary-selected base in the ordinary flow was rejected because the
  Change-owned state already provides the default. Requiring a clean or
  separate worktree was rejected because it is not necessary for exact
  identity binding.

### Decision: Current-only review evidence

- **Choice**: Keep only each stage's current result. `Request Changes` and stale
  results leave workflow state unchanged. Primary repairs located targets,
  reruns applicable gates, freezes a new candidate, and resumes that stage's
  fixed Reviewer context for the single permitted re-review.
- **Rationale**: The workflow needs a reliable current gate, not an audit
  database. A fresh initial context prevents Primary conversation from becoming
  hidden authority; a bounded same-context re-review lets Reviewer compare the
  repair while current files and candidate identity remain authoritative.
- **Alternatives considered**: Review histories and host continuation were
  rejected because correctness should come from current files and candidate
  identity.

## Interfaces

### Review CLI

```text
ssf review candidate <change-dir> <proposal-specs|design-tasks|final> [--base <git-base>] --json
ssf review record    <change-dir> <proposal-specs|design-tasks|final> [--base <git-base>] --json
ssf review check     <change-dir> <proposal-specs|design-tasks|final> [--base <git-base>] --json
```

- `final` candidate, record, and check default to the immutable
  `execution_base_commit` captured on first entry to `executing`. `--base`
  remains an optional diagnostic or compatibility override.
- Planning candidates include current planning artifacts and upstream review/DP
  bindings where applicable.
- Final candidate includes only metadata and paths publicly; its identity binds
  current source/worktree and frozen evidence inputs internally.
- Verdict is exactly `Approved` or `Request Changes`.
- A Finding contains `severity`, project-relative `file`, positive `line`,
  `impact`, and `suggested_repair`.

### State bindings

- `dp_1_candidate_identity`
- `dp_2_candidate_identity`

No state name or transition command is added.

## Failure Handling

- Missing Reviewer, malformed JSON, wrong stage, forbidden fields, unsafe
  report transport, invalid finding path, mismatched identity, or stale input:
  return nonzero and leave current state unchanged.
- A Design/Tasks or final finding that requires changing approved upstream
  semantics: Primary asks whether to reopen the earliest affected Planning
  stage before editing upstream artifacts.
- Unexecuted real VS Code/OpenCode/internal-network validation: record
  `PENDING`; never infer a pass from static or protocol tests.

## Risks And Trade-Offs

| Risk | Mitigation |
|---|---|
| Reviewer is independent but does not execute tests or state-changing workflow commands | Reviewer runs only read-only `review candidate`, discovers real artifacts and repository evidence itself, and uses ordinary read-only SCM inspection |
| Behavioral no-mutation instructions can drift or be violated | Host registration and packed-resolution tests assert the prompt contract; OpenCode public-tool runtime proves the declared Reviewer can perform required reads while candidate identity, porcelain status, and cached diff remain unchanged; real VS Code Chat stays `PENDING` |
| Candidate changes during review | Primary freezes inputs; `review check` recomputes identity and fails stale |
| Fixed Reviewer is unavailable | Fail closed and keep workflow state unchanged |
| Full review adds latency | Limit it to three high-value checkpoints; non-full paths stay unchanged |
| Real host business flow is not rerun | Keep it `PENDING` and disclose the residual risk |
