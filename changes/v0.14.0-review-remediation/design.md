# Technical Design

## Context

- Current state: the verifier installs the tgz directly and derives some
  Plugin Chat outcomes; integrity sidecars are not trusted inputs.
- Constraints: validation must work offline, use the final tgz, avoid user
  global CLI/settings changes, and make no internal-environment claims.
- Stakeholders: workflow maintainers, developers installing the Plugin, and
  independent reviewers.

## Goals

- Fail before extraction when any bundle identity or digest field disagrees.
- Make evidence scope explicit and auditable.
- Keep source maintenance checks separate from installed CLI acceptance.
- Prevent version and package-content drift.

## Non-Goals

- Automating VS Code Chat through a simulated runtime.
- Providing a production MCP server.
- Changing company registry or credential configuration.

## Project Baseline Alignment

| Scenario | Baseline Source | Classic Implementation | Applied Constraints | Deviation |
|---|---|---|---|---|
| Untampered offline bundle passes the integrity gate | `Not configured` | Existing zero-dependency Node CLI scripts | Offline, isolated prefix, no user environment mutation | None |
| Tampered bundle metadata or archive fails before extraction | `Not configured` | Fail-closed package verification | Validate identity and digest before tar extraction | None |
| Package excludes system and temporary files | `Not configured` | npm package ignore rules | Reject forbidden entries in addition to excluding them | None |
| CLI primitives pass without claiming Plugin Chat runtime | `Not configured` | Evidence classification | Report executed facts only | None |
| Default Plugin MCP is reported as not configured | `Not configured` | Empty MCP configuration template | Fixture evidence remains test-only | None |
| Source doctor returns non-zero outside a valid source checkout | `Not configured` | Unix command exit status | Failed source checks produce non-zero | None |
| Version sync updates every workflow-init package reference | `Not configured` | Central version synchronization | All command references are checked | None |

## Requirement And Scenario Coverage

| Requirement | Scenario | Design Decision | Affected Area | Why Here |
|---|---|---|---|---|
| Offline bundles fail closed when integrity metadata is inconsistent | Untampered offline bundle passes the integrity gate | Integrity Gate | `scripts/lib/offline-bundle-integrity.mjs` | One function owns trust establishment |
| Offline bundles fail closed when integrity metadata is inconsistent | Tampered bundle metadata or archive fails before extraction | Pre-extraction Failure | verifier and integrity tests | Installation must never precede trust |
| Offline bundles fail closed when integrity metadata is inconsistent | Package excludes system and temporary files | Package Hygiene | `.npmignore`, package tests | Defense in depth prevents accidental release |
| Local evidence states only what the local runtime executed | CLI primitives pass without claiming Plugin Chat runtime | Evidence Scope | verifier evidence and docs | Evidence labels match actual execution |
| Local evidence states only what the local runtime executed | Default Plugin MCP is reported as not configured | Production MCP Default | Plugin docs and tests | No server is shipped |
| Maintenance commands and version references fail visibly | Source doctor returns non-zero outside a valid source checkout | Source Doctor Status | `cmd-doctor.mjs` and docs | Maintenance failures must be scriptable |
| Maintenance commands and version references fail visibly | Version sync updates every workflow-init package reference | Workflow Init Version Sync | version scripts and tests | Prevent stale offline commands |

## Decisions

### Decision: Integrity Gate

- **Choice**: validate manifest fields, checksum record, actual SHA-256, tar
  readability, and archive entries in one pre-extraction function.
- **Rationale**: later install tests are meaningful only after package identity
  is established.
- **Alternatives considered**: trusting `SHA256SUMS` without comparing
  `manifest.json`; rejected because both sidecars could drift independently.

### Decision: Pre-extraction Failure

- **Choice**: complete all metadata, digest, readability, and entry checks before
  calling `tar -x` or `npm install`.
- **Rationale**: a failing bundle must not create extracted or installed state.
- **Alternatives considered**: verify after extraction; rejected because that
  crosses the trust boundary too early.

### Decision: Package Hygiene

- **Choice**: exclude narrow temporary-file patterns during `npm pack` and
  reject those entries during verification.
- **Rationale**: prevention and verification cover both repository-built and
  manually assembled bundles.
- **Alternatives considered**: delete the current file only; rejected because
  recurrence would remain possible.

### Decision: Evidence Scope

- **Choice**: local scripts do not report Chat command discovery/invocation or
  rendered READY as passing.
- **Rationale**: manifest and CLI tests prove structure and primitives, not host
  behavior.
- **Alternatives considered**: infer READY from CLI version; rejected because it
  does not execute the Plugin command.

### Decision: Production MCP Default

- **Choice**: keep production `mcpServers` empty and label it `Not Configured`.
- **Rationale**: the repository ships no approved production server.
- **Alternatives considered**: promote the test fixture; rejected because it is
  a protocol/path fixture, not a product tool.

### Decision: Source Doctor Status

- **Choice**: retain current source checkout checks and make failures non-zero.
- **Rationale**: an installed CLI health command would need a different,
  explicitly designed contract.
- **Alternatives considered**: resolve package root from the installed binary;
  rejected as unrelated to the existing source-maintenance checks.

### Decision: Workflow Init Version Sync

- **Choice**: update and validate the tgz filename alongside command metadata,
  registry package version, and comparison text.
- **Rationale**: offline installation depends on the exact filename.
- **Alternatives considered**: compute the filename at Chat runtime; rejected
  because slash-command content is static text distributed in the Plugin.

## Risks And Trade-Offs

- More strict bundle validation can reject manually assembled packages ->
  require the repository builder and preserve explicit failure messages.
- npm ignore patterns can accidentally hide required files -> use narrow
  patterns and assert required Plugin files remain in the tgz.
- VS Code runtime remains unverified locally -> keep it a visible pending gate
  in the internal execution checklist.

## Migration Plan

- Rollout steps: add tests, implement gates, rebuild v0.14.0 local artifact,
  regenerate evidence, run full verification, and push the review commit.
- Rollback steps: revert the remediation commit; no published release or tag is
  modified.

## Open Questions

- None.
