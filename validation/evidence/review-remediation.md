# v0.14.0 Independent Review Remediation Evidence

## Final Distribution

- Package: `release-assets/v0.14.0/spec-superflow-0.14.0.tgz`
- SHA-256: `39a69a654c05045882bb4779ad62a4f3ea91fa3e1cac42fa49ab5c0f99bff574`
- Archive entries: 154
- Required entries present: production `.mcp.json`, OpenPlugin manifest, Agent,
  `/workflow-init`, and the integrity verifier
- Excluded: `changes/`, `tests/`, `validation/`, `release-assets/`,
  `.DS_Store`, AppleDouble, and editor temporary `.DS_Store` entries

## RED Evidence

Before implementation, the targeted suite failed on the reviewed behavior:

- Integrity module and integrity-only command did not exist.
- `ssf doctor` returned status 0 outside a source checkout.
- `ssf version 0.15.0` left `spec-superflow-0.14.0.tgz`.
- Version consistency accepted the stale tgz filename.
- Production MCP documentation lacked `Not Configured` and claimed a fixture
  Chat call.

Command:

```bash
node --test \
  tests/lib/offline-bundle-integrity.test.js \
  tests/lib/vscode-plugin-evidence.test.js \
  tests/lib/maintenance-cli.test.js
```

Initial result: 5 failed tests/process files.

## GREEN Evidence

| Gate | Command | Result |
|---|---|---|
| Integrity and evidence scope | `node --test tests/lib/offline-bundle-integrity.test.js` | Pass, 7 tests |
| MCP product/test boundary | `node --test tests/lib/vscode-plugin-evidence.test.js` | Pass, 1 test |
| Doctor and version maintenance | `node --test tests/lib/maintenance-cli.test.js` | Pass, 3 tests |
| Full suite | `npm test` | Pass, 312 tests, 0 failed |
| Final bundle install/upgrade primitives | `npm run verify:offline -- --evidence validation/evidence/offline-install-upgrade.md` | Executed local checks Pass |
| Version consistency | `node scripts/check-version-consistency.mjs` | Pass |
| Source checkout maintenance | `node scripts/spec-superflow.mjs doctor` | Pass |
| Change artifacts | `node scripts/spec-superflow.mjs validate changes/v0.14.0-review-remediation` | Pass |

## Negative Integrity Matrix

Each condition is asserted through the direct function and public
`--integrity-only` CLI path where applicable:

1. Manifest package name mismatch.
2. Manifest version mismatch.
3. Manifest Node requirement mismatch.
4. Manifest package filename mismatch.
5. Manifest digest mismatch.
6. `SHA256SUMS` filename mismatch.
7. `SHA256SUMS` digest mismatch.
8. Actual tgz digest mismatch.
9. Unreadable tgz with internally consistent sidecar digests.
10. Forbidden archive entry.

All negative cases return or throw failure before package extraction or npm
installation.

## Evidence Boundary

- Direct local tgz CLI install, repeat install, and `0.13.0 -> 0.14.0` upgrade:
  **PASS**.
- VS Code `/workflow-init` discovery, invocation, `READY`, upgrade, and second
  invocation: **PENDING VS CODE RUNTIME**.
- Production Plugin MCP: **NOT CONFIGURED**.

This document records implementation evidence only. Independent review remains
separate and has not been declared passed.
