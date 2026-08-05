# Execution Contract

## Approved Artifacts

- **Planning Lock**: `.spec-superflow.yaml > artifacts_hash` =
  `sha256:2da1c4a111ba9a39d587805676943f66c649c8c651b42d8778d2a8360915f130`

| Artifact | Source Of Truth |
|---|---|
| Proposal | `proposal.md` |
| Specs | `specs/` |
| Design | `design.md` |
| Tasks | `tasks.md` |

These approved files remain the source of truth. Do not copy their behavior, decisions, file changes, or AC test rows into this contract.

## Execution Mode

- **Mode**: `Batch Inline`
- **Selection rationale**: `tasks.md` defines two dependency-ordered Batches.
  Batch 1 produces the locally verified vendor/staging interfaces consumed by
  Batch 2; each Batch stays in the current development context with its own
  grouped RED/GREEN and regression gate.

## Batch Gates

| Batch | Entry Gate | Exit Gate | Review Gate |
|---|---|---|---|
| Batch 1 | Approved planning lock; no prior dependency | `tasks.md` Batch 1 Verification passes with per-case results | Primary verifies the frozen Batch result; final semantic review remains deferred until both Batches are complete |
| Batch 2 | Batch 1 exit gate complete and produced vendor/staging interfaces remain current | `tasks.md` Batch 2 targeted/full tests, offline package/discovery phase, connected Copilot canary phase, restoration, and package gates complete | Fixed Reviewer approves the single frozen final candidate before closing |

## Verification

AC-specific obligations remain in `tasks.md > TDD Test Plan`. Record only shared commands or procedures here.

| Check | Command Or Procedure | Evidence Required |
|---|---|---|
| Batch 1 AC tests | `node --test tests/lib/matt-plugin-vendor.test.mjs tests/lib/vscode-companion-probe.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Per-case RED/GREEN result, exit code, and grouped summary in `pr-summary.md` |
| Batch 2 AC tests | `node --test tests/lib/matt-plugin-vendor.test.mjs tests/lib/matt-vscode-plugin.test.mjs tests/lib/matt-vscode-evidence.test.mjs tests/lib/vscode-plugin-evidence.test.js tests/lib/vscode-companion-probe.test.mjs tests/lib/vscode-agent-plugin.test.mjs` | Per-case RED/GREEN result, exit code, and report path in `pr-summary.md` |
| Regression | `npm test` | Full command, exit code, passed/failed count, and no omitted suite |
| Version consistency | `node scripts/check-version-consistency.mjs` | Command, exit code, checked version, and field count |
| Source maintenance | `node scripts/spec-superflow.mjs doctor` | Command, exit code, and complete result |
| Diff hygiene | `git diff --check` | Command and exit code |
| Reproducible offline package | Run the `tasks.md` offline package/discovery procedure with an empty npm cache and unreachable registry, producing two VSIX files from the same source | Both stage manifests and file digests plus two identical full VSIX SHA-256 values; installed local roots and Agent Picker discovery; network-denial boundary |
| Connected host canaries | Run the `tasks.md` connected Copilot phase against the already installed offline VSIX while only the configured model service is allowed | Package/host identity, exact allowed-network boundary, `ask-matt` and `diagnosing-bugs` observations, no Spec/`ssf` activity, and all unexecuted statuses retained as `PENDING` |
| Environment restoration | Run the `tasks.md` isolated-profile cleanup and compare before/after host and CLI state | Before/after identities, removed profile/configuration references, and zero candidate processes |

## Frontend Verification

- **Frontend Impact**: `Yes`
- **Reason**: The change adds a visible `Matt Engineering` entry to the VS Code
  Agent Picker and requires two observable Copilot Chat behaviors.

| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
| UI Test | `Required by tasks.md` | Every UI row in `tasks.md`; automated Chat/Picker control remains unavailable | Isolated VS Code 1.123 profile | Record the searched automation gap, then execute the approved offline discovery and connected Chat procedures without substituting static tests | Per-AC result, raw trace/screenshot paths, package identity, and network boundary |
| Device Test | `Required` | Reachable dual-entry discovery, `ask-matt`, `diagnosing-bugs`, and unchanged Spec smoke; other Matt Skills and duplicate-name resolution remain external/unexecuted | Local macOS VS Code 1.123 isolated profile | Install the offline VSIX, run the two phased acceptance procedure, validate raw evidence, then restore the profile | Result, VS Code and VSIX versions/digests, executed branches, restoration proof, and explicit `PENDING` list |

## Stop Conditions

- Planning hash changes after approval.
- Required behavior, scope, or a design assumption changes.
- A planned test cannot run or fails after the allowed repair loop.
- Implementation requires an unapproved dependency, interface, or architecture deviation.
- Ordinary build/install attempts any Git, registry, MCP, URL, or content fetch.
- Repeated fixed-input stage manifests, file digests, or VSIX SHA-256 values differ.
- Sync validation, local-adaptation detection, destination safety, atomic swap, or rollback cannot be proved without partial replacement risk.
- Implementation needs Skill prefixing, duplicate-name resolution, Spec state-machine changes, or `/workflow-init` changes.
- Real VS Code evidence cannot prove both approved canaries or environment restoration; keep the result blocked/PENDING rather than infer PASS.
