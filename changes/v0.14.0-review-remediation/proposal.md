# Change Proposal

## Why

The v0.14.0 offline verification currently reports some inferred results as
runtime evidence, does not reject tampered bundle metadata, and packages an
editor temporary file. Independent review therefore cannot rely on the bundle
evidence or trace the implementation back to explicit acceptance scenarios.

## What Changes

- Verify `manifest.json`, `SHA256SUMS`, the tgz digest, archive readability, and
  forbidden package entries before extracting or installing the bundle.
- Treat `/workflow-init` Chat execution as unverified until it runs in a real
  VS Code Plugin runtime; report only locally executed CLI installation
  primitives as passing.
- Define the default Plugin MCP state as `Not Configured`; retain the fixture
  only as a protocol and `${PLUGIN_ROOT}` regression test.
- Keep `ssf doctor` as a source-checkout maintenance command, return non-zero
  on failed checks, and remove it from installed CLI acceptance evidence.
- Synchronize and validate every workflow-init version reference, including the
  offline tgz filename.
- Exclude operating-system and editor temporary files from npm packages.

## Capabilities

### New Capabilities

- offline-bundle-integrity-gate
- evidence-scope-classification

### Modified Capabilities

- workflow-init-version-sync
- source-doctor-failure-status
- plugin-mcp-default-state

## Scope

### In Scope

- Offline bundle builder, verifier, tests, evidence, and installation docs.
- Version synchronization and consistency checks for `workflow-init`.
- `ssf doctor` failure exit status and source-only documentation.
- VS Code Plugin and MCP claims in v0.14.0 documentation.

### Out of Scope

- Connecting to a company computer or validating an internal environment.
- Shipping a production MCP server.
- Creating a tag, GitHub Release, or publishing npm.
- Changing the development state machine.

## Impact

- Affected code areas: `scripts/`, `tests/lib/`, package ignore rules.
- Affected interfaces: verifier exit status and `ssf doctor` exit status.
- External systems: local npm/tar executables only; no network is required.
