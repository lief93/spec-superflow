# Technical Design

## Context

- Current state: `scripts/build-vscode-vsix.mjs` assembles one
  `extension/agent-plugin` from the npm package plus VSIX-only additions, and
  `extensions/spec-superflow-companion/package.json` declares that single root.
  `tests/lib/vscode-companion-probe.test.mjs` is the existing staged-payload
  seam; the repository has no automated VS Code Chat UI driver.
- Minimum behavior-changing production seam: add one repository-owned
  `extensions/spec-superflow-companion/matt-plugin` source tree, validate it
  through one shared vendor module, and extend only the companion manifest and
  VSIX staging path to copy it beside the unchanged Spec assembly.
- Constraints: current Proposal/Specs and DP-1 are read-only; build/install use
  no network; current upstream identity is commit
  `2ab958093e83e0ec752e6c1c5932da465bf23e0c` with 22 manifest-selected Skills;
  future sync inventory comes from the explicitly requested commit; no Skill
  prefixing or duplicate-name resolution; real `ask-matt` and
  `diagnosing-bugs` Copilot acceptance is required, while other unexecuted host
  semantics remain `PENDING`. Offline build/install/discovery evidence is
  captured before any model connection; Chat canaries may then allow only the
  configured Copilot model service while Git, registry, MCP, and content-fetch
  endpoints remain blocked.

## Requirement And Scenario Coverage

| Requirement | Scenario | Design Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Why Here |
|---|---|---|---|---|---|---|
| One offline VSIX exposes two independent Agent Plugins | User installs the complete VSIX offline | Assemble two verified Plugin roots | Companion manifest and VSIX staging | `stageVsix`, `stageAgentPlugin`, `contributes.chatPlugins` | Build reads repository-owned files only | The existing staging boundary owns installed extension layout. |
| Existing Spec Superflow behavior remains intact | User selects Spec Superflow from the dual-Plugin VSIX | Assemble two verified Plugin roots | Existing `agent-plugin` staging and regression tests | `stageAgentPlugin`, current three Language Model Tools | Matt is an additive sibling; Spec routing has no explicit Matt link | Keeping the existing assembler unchanged prevents cross-workflow coupling. |
| Matt Plugin content matches the pinned official manifest | Maintainer verifies the vendored Skill inventory | Treat manifest-selected vendor content as immutable data | Matt source tree and vendor verifier | Upstream `.claude-plugin/plugin.json` selection model | Current inventory is exactly the fixed 22 paths and 66 selected files | One verifier makes source, stage, and package use the same allowlist and digests. |
| Matt Engineering provides a usable Agent and Skill router | User explicitly invokes Ask Matt | Keep the Matt Agent thin and verify behavior at the real host boundary | Matt Agent, `ask-matt`, runtime evidence | Existing `.agent.md` frontmatter pattern and upstream Skill metadata | No new state machine and no `ssf` link | The Agent entry selects the Plugin while the original Skill remains the router. |
| Matt Engineering provides a usable Agent and Skill router | User reports a bug through Matt Engineering | Keep the Matt Agent thin and verify behavior at the real host boundary | Matt Agent, `diagnosing-bugs`, runtime evidence | Existing model-invoked Skill metadata | Real Chat proof is required; static prompt checks are insufficient | Model invocation is observable only in the host that performs Skill selection. |
| Vendored content has auditable license and provenance | Reviewer audits a built package without network access | Treat manifest-selected vendor content as immutable data | MIT license, provenance, staged verifier | Existing SHA-256 and package-hygiene patterns | Audit must work from packaged bytes | Digests bind the upstream identity and every selected packaged file. |
| Normal build and installation are offline and deterministic | Maintainer repeats the build with network unavailable | Assemble two verified Plugin roots | Stage normalization and VSIX writer | Existing `stageVsix`, local `npm pack`, and `zip -X` | Fixed inputs must yield identical VSIX bytes | Staging is the only point that can normalize inventory, mode, order, and timestamp. |
| Upstream synchronization is explicit and fails safely | Maintainer proposes an acceptable pinned revision | Share validation between build and transactional sync | Sync CLI and vendor module | Existing Node.js built-ins and temporary-directory patterns | Requested manifest may contain a count other than 22 | The sync adapter fetches; the shared core validates and reports the proposed inventory. |
| Upstream synchronization is explicit and fails safely | Synchronization encounters unsafe or conflicting input | Share validation between build and transactional sync | Sync preflight, same-parent temporary tree, rollback | Existing path-boundary and digest-validation patterns | Never partially replace or silently overwrite vendor files | Full preflight and digest-based local-drift detection happen before the single swap. |
| Host compatibility claims remain evidence-based | Packaged Skill uses host-specific or subagent semantics | Separate compatibility status from source preservation | Packaged compatibility ledger and docs | Existing `PENDING` evidence language | Remaining 20 Skills are not promoted by structural tests | A ledger can describe support without rewriting upstream source or overstating runtime. |
| Host compatibility claims remain evidence-based | Installed Plugins contain the same Skill name | Separate compatibility status from source preservation | Compatibility ledger and package checks | Existing unprefixed `grill-me` in both roots | Host resolution remains `PENDING`; no prefix or resolver | The package records the collision but does not claim host routing behavior. |
| Host compatibility claims remain evidence-based | Real Copilot runtime evidence is recorded | Keep the Matt Agent thin and verify behavior at the real host boundary | Raw runtime evidence and evidence checker | Existing real-runtime evidence discipline | Evidence is package- and host-bound; no inference to unexecuted Skills | A fail-closed checker separates executed results from structural gates. |

## Decisions

### Decision: Treat manifest-selected vendor content as immutable data

- **Choice**: Store the upstream manifest-selected Skill directories under the
  Matt Plugin source root without rewriting `SKILL.md`; add the upstream MIT
  license and a generated provenance file containing repository, commit,
  upstream version, manifest path, selected paths, and per-file SHA-256.
- **Rationale**: Original content stays auditable, while one exact manifest and
  digest set detects omissions, additions, and local edits.
- **Alternatives considered**: Copy the whole upstream repository imports
  excluded content; rewriting Skills loses provenance; a binary archive makes
  Plugin loading and review harder.

### Decision: Share validation between build and transactional sync

- **Choice**: Put path, manifest, license, inventory, and digest checks in
  `scripts/lib/matt-plugin-vendor.mjs`. The ordinary build calls only its local
  verifier. `scripts/sync-matt-plugin.mjs` is the sole network-capable adapter:
  it resolves an explicit commit into a temporary source, produces a proposed
  inventory/diff, rejects local digest drift, validates a same-parent temporary
  destination, then swaps only the vendor-owned subtree with rollback.
- **Rationale**: Build and sync cannot drift on what constitutes a valid Matt
  payload, and no fetch code is reachable from build/install.
- **Alternatives considered**: Separate verifiers duplicate security rules;
  copying directly into the live tree permits partial updates; requiring every
  future manifest to contain 22 Skills prevents legitimate official changes.

### Decision: Assemble two verified Plugin roots

- **Choice**: Preserve `stageAgentPlugin` for Spec, add a Matt staging function
  that verifies then copies the repository-owned Matt root, declare exactly two
  `chatPlugins`, and normalize staged file order, modes, and timestamps before
  creating the VSIX.
- **Rationale**: The additive sibling seam minimizes Spec regression risk and
  makes repeated local builds byte reproducible.
- **Alternatives considered**: Merging Skills into `agent-plugin` breaks
  isolation; a second VSIX violates the one-install goal; fetching during build
  fails offline use.

### Decision: Keep the Matt Agent thin and verify behavior at the real host boundary

- **Choice**: Add one user-invocable `Matt Engineering` Agent that links the
  packaged original Skills, adds no workflow state, subagent implementation, or
  `ssf` dependency, and validate `ask-matt` plus `diagnosing-bugs` in real VS
  Code Copilot. Record package digest, host version, Agent, Skill selection,
  response, filesystem/command observations, and the exact network boundary in
  raw evidence checked by a deterministic evidence validator. Run offline
  build/install/discovery first; only then allow the configured model service
  for Chat while upstream Git, registry, MCP, and content fetch stay blocked.
- **Rationale**: Static packaging proves availability but only the real host can
  prove user- and model-invocation semantics.
- **Alternatives considered**: A new orchestrator duplicates upstream routing;
  static prompt matching cannot prove Skill selection; claiming all 22 Skills
  from two canaries overstates coverage.

### Decision: Separate compatibility status from source preservation

- **Choice**: Package a compatibility ledger and bilingual guidance that mark
  source-preserved constructs separately from real runtime status. Keep
  `code-review`, `research`, `wayfinder`, other unexecuted Skills, and duplicate
  `grill-me` resolution `PENDING` until their own evidence exists.
- **Rationale**: Users can see what is shipped, adapted, executed, or unknown
  without changing original Skill names or text.
- **Alternatives considered**: Deleting unsupported constructs damages source
  fidelity; treating structural checks as PASS creates false runtime claims;
  automatic prefixing exceeds the approved scope.

## Risks And Trade-Offs

- Upstream Skills may reference host features Copilot does not implement ->
  preserve source and mark each unexecuted semantic `PENDING`; prove only the
  two required canaries.
- `grill-me` exists in both roots -> verify that no automatic resolver or rename
  is introduced and keep actual host resolution `PENDING`.
- A sync interruption could corrupt the vendor tree -> complete all validation
  in a same-parent temporary tree, reject local drift, and retain rollback until
  the replacement verifies.
- ZIP tools can embed nondeterministic metadata -> normalize path order, modes,
  and timestamps and assert equal staged manifests and VSIX SHA-256 across two
  offline builds.
- A Matt addition could regress Spec packaging -> retain the existing Spec
  staging function and extend its current package tests rather than sharing
  Matt routing or state.
- Treating Copilot inference as offline would make the canaries impossible ->
  separate forced-offline package/discovery acceptance from connected Chat
  canaries and record the allowlisted model-service boundary explicitly.
