# PR Summary

## Delivered Scope

- Delivered: one deterministic offline VSIX with independent Spec Superflow and
  Matt Engineering Plugin roots; 22 pinned upstream Skills/66 selected files;
  provenance, MIT license, fail-closed verification, explicit sync, two real
  Matt canaries, and unchanged Spec routing smoke.
- Not included: Skill prefixing, duplicate-name resolution, Spec state-machine
  or `/workflow-init` changes, release, publication, or compatibility promotion
  for the other 20 Matt Skills.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| Batch 1 AC tests | Pass | `node --test tests/lib/matt-plugin-vendor.test.mjs tests/lib/vscode-companion-probe.test.mjs tests/lib/vscode-agent-plugin.test.mjs`; exit 0. |
| Batch 2 AC tests | Pass | Six-suite scoped command; 47/47, exit 0. |
| Full regression | Pass | `npm test`; 479/479, exit 0. |
| Version consistency | Pass | `node scripts/check-version-consistency.mjs`; all 12 manifest fields at 0.15.0, exit 0. |
| Source maintenance | Pass | `node scripts/spec-superflow.mjs doctor`; all checks passed, exit 0. |
| Artifact validate | Pass | `node scripts/spec-superflow.mjs validate changes/matt-workflow-plugin`; 5/5 artifacts valid, exit 0; evidence in this table and command output. |
| State check | Pass | `node scripts/spec-superflow.mjs state check changes/matt-workflow-plugin`; stored/current `sha256:2da1c4a111ba9a39d587805676943f66c649c8c651b42d8778d2a8360915f130`, exit 0. |
| Diff hygiene | Pass | `git diff --check`; exit 0. |
| Offline package | Pass | `evidence/offline-package/summary.md`; two empty-cache/unreachable-registry builds produced the same 256-file stage and VSIX SHA-256 `31a3c6f2af20d7238933469e6ca5acef006c6938904ce281f8677f1ec88988ef`. |
| Runtime acceptance | Pass | `node scripts/check-matt-vscode-evidence.mjs changes/matt-workflow-plugin/evidence/runtime/raw-evidence.json`; two canaries, Spec smoke, and restoration accepted, exit 0; `runtime-evidence.md`. |
| Package hygiene | Pass | `npm pack --dry-run --json --ignore-scripts`; 183 entries, exit 0. |

## AC Test Evidence

| Requirement | AC | Layer | Platform | Test File | Test Case | Result | Command | Evidence |
|---|---|---|---|---|---|---|---|---|
| Matt Plugin content matches the pinned official manifest | Maintainer verifies the vendored Skill inventory | Integration | Node.js 22 | tests/lib/matt-plugin-vendor.test.mjs | matches the pinned official 22-Skill inventory and all selected resources | Pass | `node --test tests/lib/matt-plugin-vendor.test.mjs` | Exact 22 Skills and 66 selected files accepted; scoped suite exit 0. |
| Vendored content has auditable license and provenance | Reviewer audits a built package without network access | Integration | Node.js 22 | tests/lib/matt-plugin-vendor.test.mjs | audits packaged MIT provenance and rejects any inventory or digest drift | Pass | `node --test tests/lib/matt-plugin-vendor.test.mjs` | Valid package accepted; missing, extra, and changed fixtures rejected; exit 0. |
| Normal build and installation are offline and deterministic | Maintainer repeats the build with network unavailable | Integration | Node.js 22 / macOS VSIX tooling | tests/lib/vscode-companion-probe.test.mjs | builds identical staged digests and VSIX bytes twice in npm offline mode | Pass | `node --test tests/lib/vscode-companion-probe.test.mjs` | Two offline builds and explicit final evidence both produced identical stage and VSIX bytes. |
| Upstream synchronization is explicit and fails safely | Maintainer proposes an acceptable pinned revision | Integration | Node.js 22 | tests/lib/matt-plugin-vendor.test.mjs | proposes every official manifest inventory change for an explicit future commit | Pass | `node --test tests/lib/matt-plugin-vendor.test.mjs` | Fixture reports exact add/remove/rename/count delta; exit 0. |
| Upstream synchronization is explicit and fails safely | Synchronization encounters unsafe or conflicting input | Integration | Node.js 22 | tests/lib/matt-plugin-vendor.test.mjs | preserves the complete current vendor tree on every unsafe or conflicting sync failure | Pass | `node --test tests/lib/matt-plugin-vendor.test.mjs` | Traversal, identity, drift, destination, swap, and rollback failures preserve before/after digest. |
| One offline VSIX exposes two independent Agent Plugins | User installs the complete VSIX offline | Integration | Node.js 22 / VSIX layout | tests/lib/vscode-companion-probe.test.mjs | contributes exactly two Agent Plugins plus unchanged CLI bootstrap and Example MCP tools | Pass | `node --test tests/lib/vscode-companion-probe.test.mjs` | Stage contains exactly `agent-plugin` and `matt-plugin`; existing three tools remain. |
| One offline VSIX exposes two independent Agent Plugins | User installs the complete VSIX offline | UI | VS Code 1.123 Chat | Not configured | Searched extension test host and tests for an Agent Picker automation API; none can install a VSIX and drive Copilot Chat | Unavailable | Repository and VS Code host API search | Automation gap retained; real isolated Agent Picker discovery passed and is recorded in `runtime-evidence.md`. |
| Existing Spec Superflow behavior remains intact | User selects Spec Superflow from the dual-Plugin VSIX | Integration | Node.js 22 / VSIX layout | tests/lib/vscode-companion-probe.test.mjs | stages a self-contained Agent Plugin without a native MCP dependency | Pass | `node --test tests/lib/vscode-companion-probe.test.mjs` | Spec payload/tools/CLI assertions pass with no Matt route. |
| Existing Spec Superflow behavior remains intact | User selects Spec Superflow from the dual-Plugin VSIX | UI | VS Code 1.123 Chat | Not configured | Searched extension-host and repository tests; no Copilot Agent Picker/Chat driver exists | Unavailable | Repository and VS Code host API search | Automation gap retained; real smoke loaded `workflow-start`, returned `exploring`, and made no mutation. |
| Matt Engineering provides a usable Agent and Skill router | User explicitly invokes Ask Matt | Integration | Node.js 22 / Plugin contract | tests/lib/matt-vscode-plugin.test.mjs | registers Ask Matt as an unprefixed user-invoked route with no Spec dependency | Pass | `node --test tests/lib/matt-vscode-plugin.test.mjs` | Agent links original `ask-matt` and excludes Spec/CLI routes. |
| Matt Engineering provides a usable Agent and Skill router | User explicitly invokes Ask Matt | UI | VS Code 1.123 Chat | Not configured | Searched VS Code extension-host APIs and project tests; no API exposes Copilot Skill selection or response provenance | Unavailable | Repository and VS Code host API search | Automation gap retained; real explicit canary PASS in `evidence/runtime/ask-matt-transcript.jsonl`. |
| Matt Engineering provides a usable Agent and Skill router | User reports a bug through Matt Engineering | Integration | Node.js 22 / Plugin contract | tests/lib/matt-vscode-plugin.test.mjs | preserves diagnosing-bugs as an unprefixed model-invoked Skill with no Spec dependency | Pass | `node --test tests/lib/matt-vscode-plugin.test.mjs` | Model-invoked metadata, load-first route, and no-Spec boundary pass. |
| Matt Engineering provides a usable Agent and Skill router | User reports a bug through Matt Engineering | UI | VS Code 1.123 Chat | Not configured | Searched VS Code extension-host APIs and project tests; no API reports automatic Copilot Skill selection | Unavailable | Repository and VS Code host API search | Automation gap retained; real automatic canary PASS in `evidence/runtime/diagnosing-bugs-transcript.jsonl`. |
| Host compatibility claims remain evidence-based | Packaged Skill uses host-specific or subagent semantics | Integration | Node.js 22 / documentation contract | tests/lib/vscode-plugin-evidence.test.js | keeps authoritative VSIX docs and CHANGELOG aligned with Matt runtime statuses | Pass | `node --test tests/lib/vscode-plugin-evidence.test.js` | Authoritative docs preserve canary/PENDING boundary; exit 0. |
| Host compatibility claims remain evidence-based | Installed Plugins contain the same Skill name | Integration | Node.js 22 / Plugin contract | tests/lib/matt-vscode-plugin.test.mjs | preserves both grill-me names while duplicate host resolution remains PENDING | Pass | `node --test tests/lib/matt-vscode-plugin.test.mjs` | Both names remain unprefixed and compatibility status remains PENDING. |
| Host compatibility claims remain evidence-based | Real Copilot runtime evidence is recorded | Integration | Node.js 22 | tests/lib/matt-vscode-evidence.test.mjs | accepts only package-bound per-Skill evidence and rejects inferred or incomplete PASS | Pass | `node --test tests/lib/matt-vscode-evidence.test.mjs` | Fail-closed evidence schema tests pass 3/3; real checker accepts exact package-bound evidence. |

## Frontend Verification Evidence

- **Frontend Impact**: `Yes`
- **Reason**: The VSIX adds the visible `Matt Engineering` Agent and two
  observable Chat behaviors.

| Check | Planned Obligation | Result | Environment | Command Or Procedure | Evidence |
|---|---|---|---|---|---|
| UI Test | `Required by tasks.md` | `Unavailable` | VS Code extension test host / repository tests | Search for an Agent Picker and Copilot Chat automation API | No supported driver was found; the capability gap remains explicit and was not replaced by static PASS. |
| Device Test | `Required` | `Pass` | Local macOS, VS Code 1.123.0 isolated profile | Install final offline VSIX; select both Agents; run explicit `ask-matt`, automatic `diagnosing-bugs`, and Spec smoke; validate raw evidence; restore environment | `runtime-evidence.md`, three transcripts/screenshots, exact VSIX digest, checker PASS, before/after environment identity equal, candidate process/config reference count 0. |

## Exceptions And Known Risks

- The 20 unexecuted Matt Skills remain `PENDING`.
- Duplicate unprefixed `grill-me` host resolution remains `PENDING`.
