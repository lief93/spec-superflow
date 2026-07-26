# Offline Install and Upgrade Evidence

- Current version: `0.14.0`
- Previous version: `0.13.0`
- Network mode: npm `--offline` with registry forced to `127.0.0.1:9`
- Installation prefix: isolated temporary directory
- User global CLI and VS Code settings: unchanged

| Check | Actual | Expected | Result |
|---|---|---|---|
| Plugin manifest version | `0.14.0` | `0.14.0` | PASS |
| OpenPlugin manifest version | `0.14.0` | `0.14.0` | PASS |
| workflow-init target version | `0.14.0` | `0.14.0` | PASS |
| workflow-init offline package option | `present` | `present` | PASS |
| Plugin MCP configuration | `present` | `present` | PASS |
| Clean environment before workflow-init | `CLI missing` | `CLI missing` | PASS |
| Plugin-only plus explicit local package to CLI installation | `0.14.0` | `0.14.0` | PASS |
| workflow-init READY result | `READY` | `READY` | PASS |
| Previous CLI installation | `0.13.0` | `0.13.0` | PASS |
| Offline CLI upgrade | `0.14.0` | `0.14.0` | PASS |
| Installed CLI doctor | `passed` | `passed` | PASS |
| Idempotent second workflow-init | `skip install` | `skip install` | PASS |

Overall: **PASS**
