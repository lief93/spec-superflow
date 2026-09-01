# Harmony Quality CLI

## Problem Statement

HarmonyOS projects without an established PR quality platform lack one deterministic local command that proves tests are meaningful, changed code is covered, and new code meets explicit quality thresholds. Existing AI reviews are not reproducible enough to block delivery and often hide the evidence behind a score.

## Solution

Provide a standalone, offline-first `harmony-quality` CLI. It discovers project capabilities without guessing, runs configured build and test commands, normalizes test and coverage evidence, analyzes ArkTS quality, performs bounded changed-code mutation testing, and produces traceable JSON and Markdown reports with deterministic quality gates.

## User Stories

1. As a Harmony developer, I want project commands discovered or marked unresolved, so that the tool never invents an invalid build command.
2. As a Harmony developer, I want unit, acceptance, UI, coverage, and mutation results distinguished from infrastructure failures, so that a broken environment is not reported as a code defect.
3. As a reviewer, I want every acceptance criterion linked to an executable test, so that apparent coverage cannot hide missing behavior.
4. As a reviewer, I want changed-line coverage, CRAP, mutation, lint, duplication, complexity, and architecture findings, so that test and code quality are assessed together.
5. As a reviewer, I want every score and gate traced to metrics and file-level evidence, so that results are explainable rather than subjective.
6. As an automation author, I want stable JSON, exit codes, scopes, and ordering, so that the tool can later be integrated without changing its analysis model.

## Implementation Decisions

- The package is independent from Spec Superflow, plugins, skills, hooks, PR systems, and Sonar servers.
- Public seams are CLI process behavior and the versioned JSON report contract.
- Commands are argv arrays and run without a shell.
- Project discovery only records commands whose tasks can be verified; unresolved commands remain editable configuration.
- Hypium command success is determined from its native result summary when configured; an Hvigor exit code of zero alone is not proof that assertions passed.
- Coverage accepts LCOV and native DevEco `coverageReport.json` evidence.
- `check` supports `changed`, `module`, and `full` scopes and emits `PASS`, `FAIL`, or `BLOCKED`.
- Issues use normalized identifiers and trace to rule, metric, file, line, evidence, source, and remediation.
- Scores are deterministic summaries. Only explicit deterministic gate conditions can fail the run.
- Generated starter gates require functionality 90, reliability 90, maintainability 80, test quality 80, and overall 85; repositories may edit these explicit values.
- Markdown issue and project-stack locations use local VS Code file links; JSON retains complete structured failure stacks for audit and other integrations.
- Mutation runs against production `src/main` code in an isolated copy, preserves installed dependencies, and verifies that the source project is unchanged.
- ArkTS built-in analysis is transparent lexical analysis, not compiler-level AST analysis.

## Testing Decisions

- Test CLI behavior in temporary Harmony repositories through spawned processes.
- Assert report values against worked fixtures, not implementation-derived expectations.
- Cover path spaces, missing commands, process failure, assertion failure with process exit zero, timeout, malformed or stale evidence, deterministic output, and source isolation.
- Validate a real Harmony repository read-only after fixture coverage is green.

## Out of Scope

- Git hooks, CI, PR decoration, workflow routing, Sonar-compatible export, a Sonar server, and AI-generated fixes.
- Automatic installation of SDKs, devices, project dependencies, or missing commands.
- AI-generated scores as gate inputs.

## Further Notes

Exact Harmony commands vary by project and SDK version. Generated configuration is a verified starting point that developers may edit.
