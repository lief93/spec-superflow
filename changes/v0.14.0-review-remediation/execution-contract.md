# Execution Contract

## Intent Lock

- **Change name**: v0.14.0 review remediation
- **Problem to solve**: Offline evidence currently overstates runtime coverage,
  trusts unchecked sidecars, and lacks reviewable requirement traceability.
- **In scope**: Integrity gates, evidence classification, MCP default-state
  correction, doctor exit status, version sync, package exclusions, and
  complete review artifacts.
- **Out of scope**: Remote/internal execution, production MCP implementation,
  tag/release/npm publication, and workflow-state redesign.

## Approved Behavior

- **Approved requirement summary**: Fail closed on package inconsistency and
  report only evidence that was actually executed.
- **Key scenarios**: Valid bundle; complete tamper matrix; clean package
  contents; CLI-vs-Chat evidence split; MCP not configured; doctor failure
  status; full workflow-init version synchronization.
- **Acceptance checks**: Exact tests below, final tgz positive verification,
  negative tamper verification, full suite, consistency gate, source doctor,
  and artifact validation.

## Requirement Traceability

| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|
| Offline bundles fail closed when integrity metadata is inconsistent | Verify identity, digest, archive, and entries before extraction | Positive bundle plus every negative tamper and forbidden-entry case | Batch 1 |
| Local evidence states only what the local runtime executed | CLI primitives pass; Chat pending; production MCP not configured | Evidence and documentation regression assertions | Batch 2 |
| Maintenance commands and version references fail visibly | Source doctor fails non-zero; version sync covers tgz references | Public CLI negative test and 0.14 -> 0.15 sync tests | Batch 3 |

## AC Test Matrix

| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|---|---|
| Offline bundles fail closed when integrity metadata is inconsistent | Untampered offline bundle passes the integrity gate | Unit | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `accepts a consistent manifest checksum and readable archive` | Valid bundle returns its package path and entries |
| Offline bundles fail closed when integrity metadata is inconsistent | Untampered offline bundle passes the integrity gate | Integration | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `integrity-only CLI exits zero for a valid bundle` | CLI gate succeeds without installation |
| Offline bundles fail closed when integrity metadata is inconsistent | Tampered bundle metadata or archive fails before extraction | Unit | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `rejects every inconsistent manifest checksum and archive field` | Every reviewed tamper condition throws before extraction |
| Offline bundles fail closed when integrity metadata is inconsistent | Tampered bundle metadata or archive fails before extraction | Integration | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `integrity-only CLI exits non-zero for every tampered bundle` | Public verifier fails closed |
| Offline bundles fail closed when integrity metadata is inconsistent | Package excludes system and temporary files | Integration | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `npm package excludes system and editor temporary files` | Final package cannot contain the reviewed temporary file |
| Offline bundles fail closed when integrity metadata is inconsistent | Package excludes system and temporary files | Unit | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `rejects forbidden package entries` | Manually assembled unsafe archives fail |
| Local evidence states only what the local runtime executed | CLI primitives pass without claiming Plugin Chat runtime | Unit | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `evidence does not infer VS Code command results` | Local output contains pending runtime labels and no simulated READY pass |
| Local evidence states only what the local runtime executed | Default Plugin MCP is reported as not configured | Unit | Node.js | Add | `tests/lib/vscode-plugin-evidence.test.js` | `reports the production MCP as not configured` | Product docs cannot claim a default callable MCP |
| Maintenance commands and version references fail visibly | Source doctor returns non-zero outside a valid source checkout | Integration | Node.js | Add | `tests/lib/maintenance-cli.test.js` | `doctor exits non-zero outside a source checkout` | Failed maintenance checks are visible to automation |
| Maintenance commands and version references fail visibly | Version sync updates every workflow-init package reference | Integration | Node.js | Add | `tests/lib/maintenance-cli.test.js` | `updates every workflow-init reference from 0.14.0 to 0.15.0` | No old tgz filename survives sync |
| Maintenance commands and version references fail visibly | Version sync updates every workflow-init package reference | Integration | Node.js | Add | `tests/lib/maintenance-cli.test.js` | `consistency check rejects a stale workflow-init tgz filename` | CI detects package command drift |

## Design Constraints

- **Project baseline source**: Not configured
- **Selected classic implementations**: Existing zero-dependency Node CLI and
  isolated offline npm prefix.
- **Approved deviations**: None
- **Project Memory source**: Not configured
- **Technology constraints**: Node.js >=22; built-in modules only.
- **Architecture constraints**: Package trust established before extraction;
  fixture tests remain separate from production configuration.
- **Data and interface constraints**: Sidecar fields and archive name must agree
  exactly with `package.json`.
- **Dependency constraints**: Local `npm` and `tar`; no network.
- **Reuse targets and extension points**: Existing builder, verifier, version
  command, consistency checker, and doctor aggregation.
- **Runtime and platform facts**: Real VS Code Chat execution is not available
  as deterministic local CLI evidence.

## Task Batches

### Batch 1

- **Goal**: Establish offline package integrity and clean package contents.
- **Inputs**: Current builder, verifier, final tgz, manifest, checksum file.
- **Outputs**: Pre-extraction integrity module, exclusions, positive/negative tests.
- **Done when**: Every tamper case exits non-zero and final tgz passes.

### Batch 2

- **Goal**: Correct local runtime and MCP evidence.
- **Inputs**: Empty production MCP and actual executed local commands.
- **Outputs**: Scoped evidence and corrected docs/tests.
- **Done when**: No local PASS implies VS Code Chat or production MCP execution.

### Batch 3

- **Goal**: Make maintenance and version failures deterministic.
- **Inputs**: Current doctor and version scripts.
- **Outputs**: Non-zero doctor failure and full workflow-init version coverage.
- **Done when**: Empty-dir doctor and stale tgz tests fail correctly.

### Batch 4

- **Goal**: Regenerate reviewable evidence and close implementation.
- **Inputs**: Completed code and tests.
- **Outputs**: Final package, evidence, PR summary, review focus, known risks.
- **Done when**: All local gates pass and pending runtime items remain explicit.

## Test Obligations

- **Behavior that must start with a failing test**: Integrity tamper matrix,
  package exclusion, doctor exit code, version package reference sync, and
  evidence-scope assertions.
- **Required edge cases**: Every manifest field, both checksum representations,
  actual digest, unreadable archive, forbidden entry, invalid source checkout,
  and stale tgz reference.
- **Regression-sensitive areas**: Offline installation, npm package contents,
  Plugin manifest structure, and all version declarations.

## Frontend Verification

- **Frontend Impact**: No
- **Reason**: This change affects distribution scripts, CLI status, and
  documentation; it does not modify an application UI.

## Execution Mode

- **Mode**: SDD
- **Selection rationale**: Independent review identified cross-cutting evidence,
  packaging, CLI, and documentation failures that require traceable batches.

## Verification Dimensions

| Dimension | Status | Findings |
|---|---|---|
| Completeness | Pass | Every AC has exact test evidence in `pr-summary.md` |
| Correctness | Pass | Positive, tamper, process-exit, and version-drift tests pass |
| Coherence | Pass | Docs, evidence labels, package, and version references agree |

**Overall conclusion**: Ready for independent rereview; review approval is not
claimed by this implementation.

## Review Gates

- **Mandatory review points**: Integrity before extraction; evidence labels;
  production/test MCP boundary; doctor semantics; version sync; final tar list.
- **Blocking categories**: Any simulated runtime PASS, unchecked metadata field,
  zero exit on failed source checks, stale version, or forbidden package entry.

## Escalation Rules

- **When to return to `specifying`**: Product requirements indicate a production
  MCP should ship or VS Code runtime evidence becomes mandatory locally.
- **When to return to `bridging`**: Test matrix or package trust boundary changes.
- **When implementation must not continue**: A fix requires remote/internal
  access, tag/release creation, or npm publication.
