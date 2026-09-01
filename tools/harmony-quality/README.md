# Harmony Quality CLI

`harmony-quality` runs deterministic HarmonyOS tests and code-quality checks, then writes traceable JSON and Markdown reports. It does not require an LLM and is not connected to Spec Superflow, Git hooks, CI, PRs, or Sonar.

For an end-to-end setup and daily-use walkthrough, see the
[Usage Guide](docs/usage.md).

## 1. Initialize

From this package directory:

```bash
node bin/harmony-quality.mjs init --project /path/to/harmony-project
```

This creates `harmony-quality.config.json` in the target project. It discovers directories containing `src/main/ets`. A local executable `hvigorw` is probed before any task is recorded. Commands that cannot be verified stay `unresolved`; the CLI does not invent commands.

Running `init` again preserves the edited configuration and reports `ALREADY_CONFIGURED`. Use `--force` only when intentionally regenerating it.

The generated configuration includes practical starter gates. They are strict
for behavior and reliability, while allowing a modest maintainability budget:

| Score | Default minimum | What to fix when it fails |
| --- | ---: | --- |
| Functionality suitability | 90 | Link every acceptance criterion to a passing executable behavior test. |
| Reliability | 90 | Resolve blocker and critical reliability findings. |
| Maintainability | 80 | Reduce smells, duplication, excessive complexity, and high-CRAP functions. |
| Test quality | 80 | Cover changed branches and add tests that kill surviving mutants. |
| Overall | 85 | Resolve the failed category gates first. |

These are editable `qualityGates` in `harmony-quality.config.json`, not hidden
constants. Teams can raise or lower them with an explicit repository change.

## 2. Configure Evidence

Commands are argv arrays and never shell strings:

```json
{
  "commands": {
    "unitTest": {
      "status": "verified",
      "required": true,
      "timeoutMs": 120000,
      "hypiumResultPath": "entry/.test/default/intermediates/test/coverage_data/test_result.txt",
      "argv": ["./hvigorw", "test", "-p", "module=entry", "-p", "coverage=true"]
    },
    "uiTest": {
      "status": "verified",
      "required": true,
      "timeoutMs": 300000,
      "infrastructureExitCodes": { "42": "device-unavailable" },
      "argv": ["./scripts/run-ui-tests.sh"]
    }
  },
  "evidence": {
    "tests": [
      {
        "id": "unit",
        "format": "hypium-text",
        "path": "entry/.test/default/intermediates/test/coverage_data/test_result.txt"
      },
      { "id": "ui", "format": "test-json", "path": "quality/ui-tests.json" }
    ],
    "acceptance": { "path": "quality/acceptance.json" },
    "coverage": {
      "format": "harmony-coverage-json",
      "path": "entry/.test/default/outputs/test/reports/coverageReport.json"
    },
    "linter": { "format": "arkts-json", "path": "quality/arkts-lint.json" }
  }
}
```

DevEco's local Hypium runner may return process exit code `0` even when an
assertion fails. Set `hypiumResultPath` for unit or UI commands so the CLI reads
the generated test summary instead of treating Hvigor's exit code as sufficient.
The configured result is removed before each run to prevent stale evidence.
The same file can be configured as `hypium-text` test evidence. Its suite and
case names become stable test IDs that acceptance criteria can reference
directly, without a custom result-conversion script.

`harmony-coverage-json` reads DevEco Studio's native `coverageReport.json` directly. Use `{ "format": "lcov", "path": "coverage/lcov.info" }` when the project already produces LCOV.

The command may be a project wrapper around the actual Hypium, UiTest, or SDK command. The wrapper only needs to leave normalized evidence files:

```json
{
  "tests": [
    { "id": "loads-page", "name": "loads page", "status": "passed", "durationMs": 18 }
  ]
}
```

Acceptance criteria link to executable tests using `<source-id>:<test-id>`:

```json
{
  "criteria": [
    { "id": "AC-1", "tests": ["unit:loads-page", "ui:shows-page"] }
  ]
}
```

ArkTS linter evidence uses:

```json
{
  "issues": [
    {
      "ruleId": "arkts-no-any",
      "type": "code-smell",
      "severity": "major",
      "file": "entry/src/main/ets/Page.ets",
      "line": 12,
      "message": "Avoid any"
    }
  ]
}
```

## 3. Configure Quality Gates

Gates reference a metric, deterministic score, or filtered issue count:

```json
{
  "qualityGates": [
    {
      "id": "changed-lines-covered",
      "source": "metric",
      "key": "line_coverage",
      "operator": ">=",
      "threshold": 80,
      "required": true
    },
    {
      "id": "no-critical-reliability-issues",
      "source": "issue-count",
      "key": "critical_reliability_issues",
      "filter": { "category": "reliability", "severity": ["blocker", "critical"] },
      "operator": "==",
      "threshold": 0,
      "required": true
    }
  ]
}
```

Supported operators are `>=`, `>`, `<=`, `<`, `==`, and `!=`. A missing required metric produces `BLOCKED`; it is never assumed to be zero or 100.

## 4. Run

```bash
node bin/harmony-quality.mjs check --project /path/to/harmony-project --scope changed --base HEAD
node bin/harmony-quality.mjs check --project /path/to/harmony-project --scope module --module entry
node bin/harmony-quality.mjs check --project /path/to/harmony-project --scope full
```

Reports are written to:

- `.harmony-quality/reports/quality-report.json`
- `.harmony-quality/reports/quality-report.md`

Open the Markdown report in VS Code and click an Issue location to jump to its
exact file, line, and column. Failed Hypium tests retain their complete stack in
JSON, while the Markdown `Failure Stacks` section shows the project frames that
are useful for repair instead of dependency frames. `Required Changes` lists
the current value, target, and remediation for every failed or blocked gate.

Exit codes:

- `0`: `PASS`
- `2`: `FAIL`, behavior or a configured quality gate failed
- `3`: `BLOCKED`, required command/evidence/infrastructure is unavailable
- `4`: invalid command or configuration
- `5`: unexpected internal failure

## Mutation

Mutation is opt-in. It runs a passing baseline, copies the project to an isolated temporary directory, mutates selected production ArkTS/TypeScript under `src/main`, runs the configured test command, and verifies that the source project hash did not change. Existing `node_modules` and `oh_modules` are preserved in the isolated copy; generated build and `.test` directories are rebuilt there.

```json
{
  "mutation": {
    "enabled": true,
    "maxMutants": 20,
    "command": {
      "argv": ["./scripts/run-mutation-tests.sh"],
      "timeoutMs": 300000,
      "compileExitCodes": [2]
    }
  }
}
```

`changed` scope limits mutations to changed source files. Mutation results distinguish `killed`, `survived`, `timeout`, and `compile-error`.

## Traceability

The JSON report links:

`overall score -> category score -> metric -> issue/test/coverage/mutation evidence -> file/line/rule`.

Built-in ArkTS checks are labeled `harmony-quality` and use transparent lexical analysis. They are not presented as compiler-level AST findings. AI opinions are not used as quality-gate inputs.
