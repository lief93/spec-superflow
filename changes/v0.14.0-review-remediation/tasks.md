# Implementation Tasks

## Interfaces

### Batch 1 -> Batch 2

- **Produces**: `verifyOfflineBundleIntegrity(bundleDir, expected)` - trusted
  package path and archive entries used before extraction and installation.

### Batch 2 -> Batch 3

- **Produces**: scoped evidence labels - documentation consumes only executed
  CLI facts and explicit pending/not-configured runtime results.

## Batch 1: Fail-closed offline distribution

Depends on: None

### AC: Untampered offline bundle passes the integrity gate

- **Requirement**: Offline bundles fail closed when integrity metadata is inconsistent
- **User-visible**: No

#### File Changes

##### Create `scripts/lib/offline-bundle-integrity.mjs`

- **Responsibility**: Establish trust in bundle identity, checksum, archive
  readability, and package entries before extraction.
- **Add**: `verifyOfflineBundleIntegrity` and focused parsing helpers.
- **Used by**: `scripts/verify-offline-bundle.mjs` and integrity tests.

##### Modify `scripts/verify-offline-bundle.mjs`

- **Current responsibility**: Exercise offline installation and upgrade.
- **Change**: Run the integrity gate before extraction or npm installation.
- **Add**: An integrity-only test path that exits non-zero on validation errors.
- **Reuse**: Existing isolated prefix and offline npm execution.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `accepts a consistent manifest checksum and readable archive` | Valid bundle returns its package path and entries |
| Integration | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `integrity-only CLI exits zero for a valid bundle` | CLI gate succeeds without installation |

#### TDD Steps

- [x] **1.1 RED / Baseline: Add positive integrity tests before the verifier exists**

Run: `node --test tests/lib/offline-bundle-integrity.test.js`
Expected: FAIL because the integrity module and CLI option do not exist.

- [x] **1.2 GREEN / Preserve: Add the minimum pre-extraction verifier**

**Files**: `Create: scripts/lib/offline-bundle-integrity.mjs`, `Modify: scripts/verify-offline-bundle.mjs`

- [x] **1.3 REFACTOR: Run integrity tests**

Run: `node --test tests/lib/offline-bundle-integrity.test.js`
Expected: PASS

### AC: Tampered bundle metadata or archive fails before extraction

- **Requirement**: Offline bundles fail closed when integrity metadata is inconsistent
- **User-visible**: No

#### File Changes

##### Modify `tests/lib/offline-bundle-integrity.test.js`

- **Current responsibility**: Verify the offline distribution trust boundary.
- **Change**: Add one negative CLI case for every manifest, checksum, digest,
  filename, Node, and archive corruption condition.
- **Reuse**: Shared temporary valid-bundle factory.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `rejects every inconsistent manifest checksum and archive field` | Every reviewed tamper condition throws before extraction |
| Integration | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `integrity-only CLI exits non-zero for every tampered bundle` | Public verifier fails closed |

#### TDD Steps

- [x] **1.4 RED / Baseline: Add the complete tamper matrix**

Run: `node --test tests/lib/offline-bundle-integrity.test.js`
Expected: FAIL for unimplemented validation branches.

- [x] **1.5 GREEN / Preserve: Enforce every identity and digest comparison**

**Files**: `Modify: scripts/lib/offline-bundle-integrity.mjs`

### AC: Package excludes system and temporary files

- **Requirement**: Offline bundles fail closed when integrity metadata is inconsistent
- **User-visible**: No

#### File Changes

##### Create `.npmignore`

- **Responsibility**: Exclude only known operating-system and editor temporary
  files from npm distributions.
- **Add**: Narrow `.DS_Store`, AppleDouble, and temporary `.DS_Store` patterns.
- **Used by**: `npm pack`.

##### Modify `tests/lib/offline-bundle-integrity.test.js`

- **Current responsibility**: Verify package trust and contents.
- **Change**: Assert dry-run package output excludes forbidden entries and the
  integrity gate rejects an injected forbidden entry.
- **Reuse**: npm pack JSON output and archive entry validation.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `npm package excludes system and editor temporary files` | Final package cannot contain the reviewed temporary file |
| Unit | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `rejects forbidden package entries` | Manually assembled unsafe archives fail |

#### TDD Steps

- [x] **1.6 RED / Baseline: Prove current npm package contains the temporary file**

Run: `node --test tests/lib/offline-bundle-integrity.test.js`
Expected: FAIL and identify `docs/.!25091!.DS_Store`.

- [x] **1.7 GREEN / Preserve: Add narrow package exclusions**

**Files**: `Create: .npmignore`

## Batch 2: Accurate command and runtime semantics

Depends on: Batch 1

### AC: CLI primitives pass without claiming Plugin Chat runtime

- **Requirement**: Local evidence states only what the local runtime executed
- **User-visible**: No

#### File Changes

##### Modify `scripts/verify-offline-bundle.mjs`

- **Current responsibility**: Generate offline installation evidence.
- **Change**: Report clean CLI install, upgrade, and version checks as executed
  primitives; report VS Code command discovery/invocation/READY as pending.
- **Add**: None.
- **Reuse**: Actual isolated npm commands.

##### Create `changes/v0.14.0-review-remediation/pr-summary.md`

- **Responsibility**: Map every planned test case to its command and result.
- **Add**: Review remediation matrix and unresolved runtime gates.
- **Used by**: Independent reviewer.

##### Create `changes/v0.14.0-review-remediation/review-focus.md`

- **Responsibility**: Bound independent review to the original findings.
- **Add**: Finding-by-finding review checklist.
- **Used by**: Independent reviewer.

##### Create `changes/v0.14.0-review-remediation/known-risks.md`

- **Responsibility**: Preserve unresolved VS Code and internal runtime gates.
- **Add**: Explicit local limitations.
- **Used by**: Independent reviewer and internal executor.

##### Modify `validation/evidence/offline-install-upgrade.md`

- **Current responsibility**: Durable local installation evidence.
- **Change**: Separate pass, pending, and not-configured outcomes.
- **Add**: Exact scope statement.
- **Reuse**: Generated verifier result.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Node.js | Add | `tests/lib/offline-bundle-integrity.test.js` | `evidence does not infer VS Code command results` | Local output contains pending runtime labels and no simulated READY pass |

#### TDD Steps

- [x] **2.1 RED / Baseline: Assert evidence cannot call inferred Chat outcomes PASS**

Run: `node --test tests/lib/offline-bundle-integrity.test.js`
Expected: FAIL on current READY and idempotent Chat labels.

- [x] **2.2 GREEN / Preserve: Replace inferred runtime claims**

**Files**: `Modify: scripts/verify-offline-bundle.mjs`, `Modify: docs/`, `Modify: validation/evidence/`

### AC: Default Plugin MCP is reported as not configured

- **Requirement**: Local evidence states only what the local runtime executed
- **User-visible**: No

#### File Changes

##### Modify `docs/vscode-agent-plugin.md`

- **Current responsibility**: Explain Plugin deployment and optional MCP.
- **Change**: State that the production Plugin ships no MCP server and fixture
  tests are non-runtime regression tests.
- **Add**: `Not Configured` acceptance result.
- **Reuse**: Existing empty `.mcp.json`.

##### Modify `docs/vscode-agent-plugin-zh.md`

- **Current responsibility**: Chinese Plugin deployment guide.
- **Change**: Apply the same explicit production/test boundary.
- **Add**: None.
- **Reuse**: Existing empty `.mcp.json`.

##### Create `tests/lib/vscode-plugin-evidence.test.js`

- **Responsibility**: Assert the fixture remains test-only, production MCP
  stays empty, and docs report `Not Configured`.
- **Add**: Production/test boundary assertions.
- **Used by**: Full test suite.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Node.js | Add | `tests/lib/vscode-plugin-evidence.test.js` | `reports the production MCP as not configured` | Product docs cannot claim a default callable MCP |

#### TDD Steps

- [x] **2.3 RED / Baseline: Assert current default MCP language is rejected**

Run: `node --test tests/lib/vscode-plugin-evidence.test.js`
Expected: FAIL until docs and evidence state `Not Configured`.

- [x] **2.4 GREEN / Preserve: Correct MCP claims without deleting fixture coverage**

**Files**: `Modify: docs/`, `Modify: validation/evidence/`, `Create: tests/lib/vscode-plugin-evidence.test.js`

## Batch 3: Source maintenance and version consistency

Depends on: Batch 1

### AC: Source doctor returns non-zero outside a valid source checkout

- **Requirement**: Maintenance commands and version references fail visibly
- **User-visible**: No

#### File Changes

##### Modify `scripts/lib/cmd-doctor.mjs`

- **Current responsibility**: Check a spec-superflow source checkout.
- **Change**: Set a non-zero process status when any source check fails.
- **Add**: None.
- **Reuse**: Existing `hasFailure` aggregation.

##### Create `tests/lib/maintenance-cli.test.js`

- **Responsibility**: Verify public maintenance CLI process behavior.
- **Add**: Empty-directory doctor and version synchronization cases.
- **Used by**: Full test suite.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js | Add | `tests/lib/maintenance-cli.test.js` | `doctor exits non-zero outside a source checkout` | Failed maintenance checks are visible to automation |

#### TDD Steps

- [x] **3.1 RED / Baseline: Capture the current zero exit in an empty directory**

Run: `node --test tests/lib/maintenance-cli.test.js`
Expected: FAIL because current doctor exits zero.

- [x] **3.2 GREEN / Preserve: Set process exit status on failure**

**Files**: `Modify: scripts/lib/cmd-doctor.mjs`

### AC: Version sync updates every workflow-init package reference

- **Requirement**: Maintenance commands and version references fail visibly
- **User-visible**: No

#### File Changes

##### Modify `scripts/lib/cmd-version.mjs`

- **Current responsibility**: Synchronize version declarations.
- **Change**: Update `spec-superflow-<version>.tgz` command references.
- **Add**: None.
- **Reuse**: Existing workflow-init text replacement.

##### Modify `scripts/check-version-consistency.mjs`

- **Current responsibility**: Reject version drift.
- **Change**: Extract and compare the workflow-init tgz filename version.
- **Add**: None.
- **Reuse**: Existing text checks.

##### Modify `tests/lib/maintenance-cli.test.js`

- **Responsibility**: Prove `0.14.0 -> 0.15.0` synchronization in a temporary checkout.
- **Add**: Version sync and stale tgz consistency regression cases.
- **Used by**: Full test suite.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js | Add | `tests/lib/maintenance-cli.test.js` | `updates every workflow-init reference from 0.14.0 to 0.15.0` | No old tgz filename survives sync |
| Integration | Node.js | Add | `tests/lib/maintenance-cli.test.js` | `consistency check rejects a stale workflow-init tgz filename` | CI detects package command drift |

#### TDD Steps

- [x] **3.3 RED / Baseline: Add 0.14.0 -> 0.15.0 regression**

Run: `node --test tests/lib/maintenance-cli.test.js`
Expected: FAIL because the tgz filename remains `0.14.0`.

- [x] **3.4 GREEN / Preserve: Extend sync and consistency patterns**

**Files**: `Modify: scripts/lib/cmd-version.mjs`, `Modify: scripts/check-version-consistency.mjs`

- [x] **4.1 REFACTOR: Run all targeted and full tests**

Run: `npm test`
Expected: PASS

- [x] **4.2 Verify the final bundle and source checkout**

Run: `npm run pack:offline && npm run verify:offline && node scripts/check-version-consistency.mjs && node scripts/spec-superflow.mjs doctor`
Expected: PASS for executed local checks; VS Code runtime remains pending.
