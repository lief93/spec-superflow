# PR Summary: Independent Review Agents

## Delivered Scope

- Added one hidden fixed read-only Reviewer beside the existing visible Primary
  in VS Code and OpenCode.
- Added exact-full checkpoints `proposal-specs`, `design-tasks`, and `final` in
  one independent Reviewer context per stage, with at most one same-context
  repair/re-review.
- Replaced prompt-sized artifact/source copies with a body-free metadata and
  path-and-symbol handoff. Reviewer independently acquires the fixed-base SCM
  view and every untracked file through ordinary host tools. Raw write, `review
  record`, then `review check` remains mandatory after every Reviewer return
  before Primary interprets or edits.
- Made Planning review overlap-first and added an explicit Android static versus
  runtime proof boundary so `getQuantityString(0/1/2)` cannot prove quantity
  selectors exist.
- Added only `ssf review candidate|record|check` with fixed safe inbox/current
  paths, strict typed results, current identity checks, and final explicit-base
  worktree identity.
- Added only DP-1/DP-2 candidate-identity bindings while retaining the existing
  DP-3 contract-hash flow.
- Kept Primary responsible for planning, implementation, tests, evidence, user
  questions, and finding repairs; kept Reviewer read-only and non-user-facing.
- Kept `/workflow-init` as the only bootstrap route and kept `hotfix`/`tweak`
  outside fixed Reviewer checkpoints.
- Removed the abandoned host-continuity and alternate orchestration design from
  production prompts, shared Skills, tests, fixtures, and current artifacts.

## Not Included

- No Dev Agent, additional user-visible role, workflow state, review-history
  service, or host continuity model.
- No Reviewer file writes, mutating Git commands, test/workflow execution, state
  mutation, user contact, MCP call, or nested Agent invocation. Read-only SCM
  inspection through ordinary host tools is required.
- No tag, release, npm publish, remote-computer access, or company-internal
  validation claim.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| Artifact validate | Pass | `node scripts/spec-superflow.mjs validate changes/independent-review-agents`; exit 0; proposal, six Specs, Design, Tasks, and contract all 0 errors and 0 warnings after simplification. |
| State check | Pass | `node scripts/spec-superflow.mjs state rebuild changes/independent-review-agents` then `state check`; exit 0; state `specifying`; stored/current artifact hash both `sha256:892742b0fca5ade56a30e42c23c9e98d5db157e6e61f4335fc29b9a0458829e3`. |
| Runtime acceptance | Pending | OpenCode 1.14.48 public Reviewer tool runtime is `1/1 PASS`: status/diff/log/show and untracked reads succeed while candidate identity, porcelain status, and cached diff remain unchanged. Pre-fix GPT-5.4 Design/Tasks E2E was `FAIL` and drove remediation; post-fix model-driven E2E, real VS Code Chat, and company-internal business flow remain unexecuted. The public tool probe does not substitute for those semantic flows. |
| Delivery package | Pass | `/tmp/spec-superflow-independent-review-gitlink-pack.bMqULr/spec-superflow-0.14.0.tgz`; SHA-256 `8315d2b411227244919962d62b76474d72c6285755b134d59614a3559e673d42`; 175 entries; archive excludes Changes, tests, validation/release assets, OS/editor junk; packaged CLI runtime 2/2 PASS and this exact archive's isolated offline global-prefix install, version, doctor, installed gitlink collector, and hygiene smoke PASS. |

Final freeze uses review base `ffa26726f555e0ccc58d95e0a64ddba3c388bf00`
and worktree identity
`sha256:1ca2acd43f4c457e79c13d54361bd7d0d1569913bd6410a7a425854b95a7c9bd`.
The collector reports 65 changed files outside this Change and cached diff 0
bytes; final review must recompute both values before acting.

Closure is non-recursive: the state artifact hash covers Proposal, Specs,
Design, and Tasks, while npm packaging excludes `changes/`. Recording these
final hash values in this summary therefore changes neither digest.

## AC Test Evidence

| Requirement | AC | Layer | Platform | Test File | Test Case | Result | Command | Evidence |
|---|---|---|---|---|---|---|---|---|
| Review CLI records only current stage evidence | Primary records a valid Reviewer result | Integration | Node.js 22 | tests/lib/cmd-review.test.mjs | records and checks 0644 and 0600 fixed inbox reports atomically | Pass | `npm test` | 422/422 PASS; both 0644 and 0600 fixed regular-file reports record and check successfully. |
| Review CLI records only current stage evidence | Review transport or result is unsafe | Integration | Node.js 22 | tests/lib/cmd-review.test.mjs | rejects symlink, directory, path override, traversal, and wrong stage inboxes | Pass | `npm test` | 422/422 PASS; every listed unsafe transport exits nonzero without replacing current evidence, including the executable no-`O_NOFOLLOW` symlink regression. |
| Review CLI records only current stage evidence | Review transport or result is unsafe | Unit | Node.js 22 | tests/lib/review-evidence.test.mjs | requires every finding line to be a positive integer | Pass | `node --test tests/lib/review-evidence.test.mjs tests/lib/managed-review-workflow.test.mjs` | 26/26 PASS; null, zero, negative, fractional, and string lines fail while a positive integer succeeds, and the canonical Reviewer prompt matches the schema. |
| Final candidate covers the complete worktree | Final work changes after approval | Integration | Git and Node.js 22 | tests/lib/worktree-review-candidate.test.mjs | final identity fails closed on semantic Git base and worktree drift | Pass | `npm test` | 422/422 PASS; semantic base and committed/staged/unstaged/untracked drift invalidate final identity. |
| Final candidate covers the complete worktree | Reviewer inspects a frozen final candidate | Integration | Git and Node.js 22 | tests/lib/review-candidate.test.mjs | keeps final candidate body-free while full tracked and untracked bytes bind identity | Pass | `node --test tests/lib/review-candidate.test.mjs tests/lib/worktree-review-candidate.test.mjs tests/lib/review-evidence.test.mjs tests/lib/cmd-review.test.mjs tests/lib/managed-review-workflow.test.mjs tests/lib/vscode-agent-plugin.test.mjs tests/lib/opencode-plugin.test.mjs` | 69/69 PASS; large tracked/untracked bodies never enter public JSON, equal-length byte changes alter identity, and unstaged-to-staged drift invalidates identity. |
| Final candidate covers the complete worktree | Reviewer inspects a frozen final candidate | Integration | Git and Node.js 22 | tests/lib/worktree-review-candidate.test.mjs | collects changed gitlink metadata without reading the submodule directory as a file | Pass | `node --test tests/lib/worktree-review-candidate.test.mjs` | 4/4 PASS; a changed local submodule produces mode `160000`, length, and content hash without exposing its source body or reading its directory as a regular file. |
| Final candidate covers the complete worktree | Reviewer inspects a frozen final candidate | Integration | Git and Node.js 22 | tests/lib/worktree-review-candidate.test.mjs | binds gitlink pointer dirty and index-status changes into final identity | Pass | `node --test tests/lib/worktree-review-candidate.test.mjs` | 4/4 PASS; commit pointer, dirty worktree, and unstaged-to-staged changes each invalidate identity and restoration is deterministic. |
| Final candidate covers the complete worktree | Reviewer inspects a frozen final candidate | Integration | OpenCode Plugin 1.14.48 | tests/integration/opencode-runtime.test.mjs | resolves hidden Agent tools through pinned OpenCode for repository and packed Plugin contexts | Pass | `node --test tests/integration/opencode-runtime.test.mjs` | 1/1 PASS; Reviewer identity executes status/diff/log/show and untracked reads while candidate identity, porcelain status, and cached diff remain byte-identical. |
| Existing state and decision-point flow remains authoritative | Planning advances through the existing state machine | Integration | Node.js 22 | tests/lib/cmd-state.test.mjs | progresses a new full-workflow Change through every mainline state | Pass | `npm test` | 422/422 PASS; a fresh Change reaches every existing mainline state with guarded transitions. |
| Full workflow uses one Primary and one fixed independent Reviewer | Primary requests an independent semantic review | Integration | VS Code and OpenCode Plugin contract | tests/lib/managed-review-workflow.test.mjs | keeps one visible Primary and one fixed read-only Reviewer | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Host targeted run: 46/46 PASS. |
| Full workflow uses one Primary and one fixed independent Reviewer | Primary requests an independent semantic review | Integration | VS Code and OpenCode Plugin contract | tests/lib/managed-review-workflow.test.mjs | hands Reviewer a bounded path index instead of inline artifact copies | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Host targeted run: 46/46 PASS; both Primary surfaces pass only exact candidate/artifact/evidence references. |
| Full workflow uses one Primary and one fixed independent Reviewer | Primary requests an independent semantic review | Integration | VS Code and OpenCode Plugin contract | tests/lib/managed-review-workflow.test.mjs | makes raw -> record -> check the only legal return sequence | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Host targeted run: 46/46 PASS; Primary and workflow-start fail closed if the return chain is skipped. |
| Full workflow uses one Primary and one fixed independent Reviewer | Non-full workflow continues | Integration | VS Code and OpenCode Plugin contract | tests/lib/managed-review-workflow.test.mjs | keeps hotfix/tweak and ordinary runtime behavior outside review/bootstrap | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Host targeted run: 46/46 PASS. |
| Planning has two independent semantic checkpoints | Proposal and Specs become ready for DP-1 | Integration | VS Code and OpenCode Plugin contract | tests/lib/managed-review-workflow.test.mjs | separates the two Planning reviews from user DP-1/DP-2 and contract DP-3 | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Host targeted run: 46/46 PASS. |
| Planning has two independent semantic checkpoints | Proposal and Specs become ready for DP-1 | Integration | VS Code and OpenCode Plugin contract | tests/lib/managed-review-workflow.test.mjs | closes Proposal and Specs against intent before first review | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Host targeted run: 46/46 PASS; overlap comparison includes surface and subset/superset relationships. |
| Planning has two independent semantic checkpoints | Design and Tasks become ready for DP-2 | Integration | Node.js 22 | tests/lib/guard-transitions.test.mjs | binds DP-2 to the current Design review for exact full workflow | Pass | `npm test` | 422/422 PASS; stale Design/Tasks approval or its DP-2 binding fails the independent-review guard. |
| Planning has two independent semantic checkpoints | Design and Tasks become ready for DP-2 | Integration | VS Code and OpenCode Plugin contract | tests/lib/managed-review-workflow.test.mjs | runs overlap preflight before the fixed Design and Tasks scan | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Host targeted run: 46/46 PASS; upstream conflict stops downstream repair and Android runtime calls are not static-selector proof. |
| VS Code and OpenCode register the same review topology | Plugin host resolves review capabilities | Integration | VS Code Agent Plugin | tests/lib/vscode-agent-plugin.test.mjs | exposes one visible Primary and one hidden fixed Reviewer | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Combined host contract run: 46/46 PASS. |
| VS Code and OpenCode register the same review topology | Plugin host resolves review capabilities | Integration | OpenCode Plugin 1.14.48 | tests/lib/opencode-plugin.test.mjs | registers one Primary, one bootstrap-only setup worker, and one behavior-read-only Reviewer | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | OpenCode contract subset PASS; source and freshly packed runtime expose ordinary Reviewer tools with the no-mutation behavioral contract. |
| Final review blocks closing without replacing mechanical gates | Final candidate is approved | Integration | VS Code and OpenCode Plugin contract | tests/lib/managed-review-workflow.test.mjs | keeps final semantic review after mechanics and before the single closing transition | Pass | `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Host targeted run: 46/46 PASS. |
| Final review blocks closing without replacing mechanical gates | Final candidate requests changes | Integration | Node.js 22 | tests/lib/cmd-review.test.mjs | keeps workflow state unchanged on Request Changes and allows repair re-review | Pass | `npm test` | 422/422 PASS; blocking verdict leaves state unchanged and repaired content receives a new current candidate. |

## Frontend Verification Evidence

- **Frontend Impact**: No
- **Reason**: Agent prompts, CLI evidence, and guards do not change an
  application UI. Real host behavior is reported separately and is not inferred
  from static tests.

## Exceptions And Known Risks

- The pre-fix model-driven Design/Tasks E2E failed on handoff size, missing
  record/check, incomplete review, upstream overlap, and static proof honesty.
  The post-fix model-driven OpenCode business flow remains `PENDING`.
- Real VS Code Chat was not rerun and remains `PENDING`.
- Company-internal validation remains user-executed and unclaimed.
- Reviewer can execute required read-only SCM inspection through ordinary host
  tools but does not run tests or workflow commands. Its no-mutation behavior is
  prompt-governed; OpenCode public-tool evidence covers the controlled read path,
  while real VS Code Chat remains `PENDING`.
