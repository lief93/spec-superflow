# PR Summary

## Delivered Scope

- Delivered: fail-closed offline bundle integrity, clean package contents,
  accurate local/runtime evidence classification, explicit production MCP
  `Not Configured` state, source-doctor non-zero failures, complete
  workflow-init version synchronization, and reviewable SDD artifacts.
- Not included: real VS Code Chat execution, a production MCP server, company
  environment validation, tag/release creation, or npm publication.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| Full automated suite | Pass, 312 tests | `npm test` |
| Final offline bundle | Pass | `npm run pack:offline` and `npm run verify:offline -- --evidence validation/evidence/offline-install-upgrade.md` |
| Final package SHA-256 | Pass | `39a69a654c05045882bb4779ad62a4f3ea91fa3e1cac42fa49ab5c0f99bff574` |
| Package entries | Pass, 154 entries | Required Plugin files present; excluded roots and temporary files absent |
| Version consistency | Pass | `node scripts/check-version-consistency.mjs` |
| Source checkout doctor | Pass | `node scripts/spec-superflow.mjs doctor` |
| SDD artifact validation | Pass | `node scripts/spec-superflow.mjs validate changes/v0.14.0-review-remediation` |
| VS Code Plugin Chat | Pending | No real host execution claimed |
| Production Plugin MCP | Not Configured | Production `.mcp.json` is empty |

## AC Test Evidence

| Requirement | AC | Layer | Platform | Test File | Test Case | Result | Command | Evidence |
|---|---|---|---|---|---|---|---|---|
| Offline bundles fail closed when integrity metadata is inconsistent | Untampered offline bundle passes the integrity gate | Unit | Node.js | `tests/lib/offline-bundle-integrity.test.js` | `accepts a consistent manifest checksum and readable archive` | Pass | `node --test tests/lib/offline-bundle-integrity.test.js` | Returned trusted package path and archive entries |
| Offline bundles fail closed when integrity metadata is inconsistent | Untampered offline bundle passes the integrity gate | Integration | Node.js | `tests/lib/offline-bundle-integrity.test.js` | `integrity-only CLI exits zero for a valid bundle` | Pass | `node --test tests/lib/offline-bundle-integrity.test.js` | Public CLI returned `Integrity: PASS` |
| Offline bundles fail closed when integrity metadata is inconsistent | Tampered bundle metadata or archive fails before extraction | Unit | Node.js | `tests/lib/offline-bundle-integrity.test.js` | `rejects every inconsistent manifest checksum and archive field` | Pass | `node --test tests/lib/offline-bundle-integrity.test.js` | Name, version, Node, filename, both digests, actual digest, and unreadable archive rejected |
| Offline bundles fail closed when integrity metadata is inconsistent | Tampered bundle metadata or archive fails before extraction | Integration | Node.js | `tests/lib/offline-bundle-integrity.test.js` | `integrity-only CLI exits non-zero for every tampered bundle` | Pass | `node --test tests/lib/offline-bundle-integrity.test.js` | Every tampered CLI fixture returned non-zero |
| Offline bundles fail closed when integrity metadata is inconsistent | Package excludes system and temporary files | Integration | Node.js | `tests/lib/offline-bundle-integrity.test.js` | `npm package excludes system and editor temporary files` | Pass | `node --test tests/lib/offline-bundle-integrity.test.js` | No excluded roots, `.DS_Store`, AppleDouble, or editor temporary entries |
| Offline bundles fail closed when integrity metadata is inconsistent | Package excludes system and temporary files | Unit | Node.js | `tests/lib/offline-bundle-integrity.test.js` | `rejects forbidden package entries` | Pass | `node --test tests/lib/offline-bundle-integrity.test.js` | Injected `package/docs/.!25091!.DS_Store` rejected |
| Local evidence states only what the local runtime executed | CLI primitives pass without claiming Plugin Chat runtime | Unit | Node.js | `tests/lib/offline-bundle-integrity.test.js` | `evidence does not infer VS Code command results` | Pass | `node --test tests/lib/offline-bundle-integrity.test.js` | Evidence source keeps Chat runtime pending and removes simulated READY/idempotency claims |
| Local evidence states only what the local runtime executed | Default Plugin MCP is reported as not configured | Unit | Node.js | `tests/lib/vscode-plugin-evidence.test.js` | `reports the production MCP as not configured` | Pass | `node --test tests/lib/vscode-plugin-evidence.test.js` | English, Chinese, and generated evidence use `Not Configured`; fixture is test-only |
| Maintenance commands and version references fail visibly | Source doctor returns non-zero outside a valid source checkout | Integration | Node.js | `tests/lib/maintenance-cli.test.js` | `doctor exits non-zero outside a source checkout` | Pass | `node --test tests/lib/maintenance-cli.test.js` | Empty-directory source check returned non-zero |
| Maintenance commands and version references fail visibly | Version sync updates every workflow-init package reference | Integration | Node.js | `tests/lib/maintenance-cli.test.js` | `updates every workflow-init reference from 0.14.0 to 0.15.0` | Pass | `node --test tests/lib/maintenance-cli.test.js` | No `0.14.0` remained, including the tgz filename |
| Maintenance commands and version references fail visibly | Version sync updates every workflow-init package reference | Integration | Node.js | `tests/lib/maintenance-cli.test.js` | `consistency check rejects a stale workflow-init tgz filename` | Pass | `node --test tests/lib/maintenance-cli.test.js` | Stale `0.14.0` tgz reference returned status 1 |

## Frontend Verification Evidence

- **Frontend Impact**: No
- **Reason**: Distribution scripts, CLI status, and documentation changed; no
  application UI changed.

## Exceptions And Known Risks

- VS Code command discovery, invocation, terminal approval UX, rendered
  `READY`, upgrade through Chat, and second Chat invocation remain pending.
- Production MCP is not configured. Fixture tests are not a production tool call.
- These pending items are documented in `known-risks.md` and
  `docs/internal-validation-prompt-zh.md`.
