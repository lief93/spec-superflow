# Offline Install and Upgrade Evidence

- Current version: `0.14.0`
- Previous version: `0.13.0`
- Network mode: npm `--offline` with registry forced to `127.0.0.1:9`
- Installation prefix: isolated temporary directory
- User global CLI and VS Code settings: unchanged
- Scope: local package integrity and CLI installation primitives only
- VS Code Plugin Chat runtime: PENDING
- Production Plugin MCP: NOT CONFIGURED

| Check | Actual | Expected | Result |
|---|---|---|---|
| Bundle integrity before extraction | `passed` | `passed` | PASS |
| Plugin manifest version | `0.14.0` | `0.14.0` | PASS |
| OpenPlugin manifest version | `0.14.0` | `0.14.0` | PASS |
| workflow-init target version | `0.14.0` | `0.14.0` | PASS |
| workflow-init offline package option | `present` | `present` | PASS |
| Production Plugin MCP | `Not Configured` | `Not Configured` | NOT CONFIGURED |
| Clean environment before local tgz CLI installation | `CLI missing` | `CLI missing` | PASS |
| Explicit local tgz CLI installation | `0.14.0` | `0.14.0` | PASS |
| Repeated local tgz CLI installation | `0.14.0` | `0.14.0` | PASS |
| Previous CLI installation | `0.13.0` | `0.13.0` | PASS |
| Offline CLI upgrade | `0.14.0` | `0.14.0` | PASS |
| VS Code command discovery and invocation | `Pending VS Code runtime` | `Pending VS Code runtime` | PENDING |
| VS Code missing-CLI install and READY rendering | `Pending VS Code runtime` | `Pending VS Code runtime` | PENDING |
| VS Code 0.13.0 upgrade and READY rendering | `Pending VS Code runtime` | `Pending VS Code runtime` | PENDING |
| VS Code second invocation and idempotent message | `Pending VS Code runtime` | `Pending VS Code runtime` | PENDING |

Executed local checks: **PASS**

This evidence does not claim that VS Code discovered or executed
`/workflow-init`, rendered `READY`, or called a production MCP tool.
