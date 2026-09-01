# Harmony Quality Usage Guide

This guide covers local installation, project setup, daily checks, report
navigation, and quality-gate adjustment. The CLI is offline-first and does not
require an LLM or a Sonar server.

## 1. Prerequisites

- Node.js 22 or newer.
- A HarmonyOS project that already builds or tests from its own terminal.
- DevEco Studio SDK environment variables required by that project.

The CLI does not install an SDK, emulator, project dependencies, or missing
build tools.

## 2. Run Directly From the Repository

From the Spec Superflow repository:

```bash
cd tools/harmony-quality
npm test
node bin/harmony-quality.mjs init --project /absolute/path/to/harmony-project
```

This is the simplest option for evaluation and development. It does not modify
global npm state.

## 3. Create an Offline Install Package

Create the package on a machine with the repository:

```bash
cd tools/harmony-quality
npm pack
```

Move `harmony-quality-0.1.0.tgz` to the target machine and install it without
contacting a registry:

```bash
npm install --global --offline ./harmony-quality-0.1.0.tgz
harmony-quality init --project /absolute/path/to/harmony-project
```

The package includes the CLI, implementation, and documentation. It does not
include tests, dependencies, caches, or project evidence.

## 4. Review the Generated Configuration

Initialization creates this file in the HarmonyOS project:

```text
harmony-quality.config.json
```

If initialization prints `manual configuration required`, replace each
`unresolved` command with the exact command that already works for that
project. Commands are argument arrays, not shell strings:

```json
{
  "commands": {
    "unitTest": {
      "status": "verified",
      "required": true,
      "timeoutMs": 180000,
      "hypiumResultPath": "entry/.test/default/intermediates/test/coverage_data/test_result.txt",
      "argv": ["./hvigorw", "test", "-p", "module=entry", "-p", "coverage=true"]
    }
  }
}
```

Do not copy a command from another project unless it has been run successfully
in the target project.

Configure native evidence produced by that command:

```json
{
  "evidence": {
    "tests": [
      {
        "id": "unit",
        "format": "hypium-text",
        "path": "entry/.test/default/intermediates/test/coverage_data/test_result.txt"
      }
    ],
    "coverage": {
      "format": "harmony-coverage-json",
      "path": "entry/.test/default/outputs/test/reports/coverageReport.json"
    }
  }
}
```

## 5. Run a Quality Check

Use changed scope for normal development:

```bash
harmony-quality check --project /absolute/path/to/harmony-project --scope changed --base HEAD
```

Use a module or the full project when needed:

```bash
harmony-quality check --project /absolute/path/to/harmony-project --scope module --module entry
harmony-quality check --project /absolute/path/to/harmony-project --scope full
```

The command writes:

```text
.harmony-quality/reports/quality-report.md
.harmony-quality/reports/quality-report.json
```

## 6. Fix a Failed Result

Open `quality-report.md` in VS Code Markdown Preview:

1. Read `Required Changes` for the current value, target, and remediation.
2. Click an Issue location to open its exact source file, line, and column.
3. For a failed Hypium test, use `Failure Stacks` to open the first project
   frame. Dependency frames remain available in the JSON report.
4. Rerun the same check after making the change.

The default score minimums are:

| Score | Minimum |
| --- | ---: |
| Functionality suitability | 90 |
| Reliability | 90 |
| Maintainability | 80 |
| Test quality | 80 |
| Overall | 85 |

Edit `qualityGates` in `harmony-quality.config.json` when a repository needs a
different explicit policy. Keep threshold changes in code review so a failing
result cannot be hidden by an unexplained local override.

## 7. Interpret Exit Codes

| Code | Meaning | Action |
| ---: | --- | --- |
| 0 | PASS | Continue delivery. |
| 2 | FAIL | Fix behavior, tests, or a failed quality gate. |
| 3 | BLOCKED | Restore the required command, evidence, SDK, or device. |
| 4 | Invalid configuration | Correct the reported configuration error. |
| 5 | Internal failure | Correct filesystem/runtime failure and rerun. |

`BLOCKED` is not a passing result. The CLI never converts missing evidence into
zero or 100.

## 8. Update Safely

Create a new tgz from the updated repository and install that exact file again:

```bash
npm install --global --offline ./harmony-quality-NEW_VERSION.tgz
harmony-quality init --project /absolute/path/to/harmony-project
```

Normal `init` preserves an existing project configuration. Use `--force` only
when intentionally replacing developer-edited commands and gates.
