# Verification Matrix

This matrix verifies the complete Harmony Quality CLI, not only coverage,
mutation score, and CRAP. Every capability requires a positive path, a negative
or boundary path, and evidence at the lowest reliable test layer.

## Test Levels

- **L1 - worked fixture:** a temporary repository with independently calculated
  expected values. This proves parser, formula, status, and schema correctness.
- **L2 - controlled Harmony requirement:** the same small ArkTS behavior is run
  through real Hvigor/Hypium with strong and weak tests. This proves that native
  evidence changes the result for the right reason.
- **L3 - existing Harmony projects:** read-only source or isolated copies of a
  single-module and a multi-module project. This proves discovery, scope, command,
  packaging, and compatibility behavior.

## Complete Capability Matrix

| ID | Capability | Positive proof | Negative or boundary proof | Level | Required evidence |
|---|---|---|---|---|---|
| HQ-01 | Harmony module discovery | Nested modules containing `src/main/ets` are returned in stable order | No Harmony module fails explicitly; generated/dependency directories are ignored | L1 + L3 | Config module list and CLI exit code |
| HQ-02 | Verified command discovery | Executable wrapper advertising a task produces an argv command | Missing, non-executable, failing, or non-advertising wrapper remains `unresolved` | L1 + L3 | Probe output and generated config |
| HQ-03 | Safe argv and paths | Project and executable paths containing spaces run successfully | Report/config paths escaping the project are rejected | L1 | Spawn result and rejected path error |
| HQ-04 | Idempotent initialization | First run creates config; `--force` intentionally regenerates it | Normal repeat preserves developer edits and reports `ALREADY_CONFIGURED` | L1 + L3 | Before/after config hashes |
| HQ-05 | Build execution | Real or fixture build exits zero and is recorded as pass | Non-zero build is `FAIL`; missing executable or timeout is `BLOCKED` | L1 + L3 | Command id, exit code, outcome, report status |
| HQ-06 | Unit-test execution | Passing Hypium/fixture command and named cases are recorded | Test failure is `FAIL`, not infrastructure failure; all skipped is not 100% | L1 + L2 | Test cases, summary, command outcome |
| HQ-07 | UI/system-test execution | Configured UI command and cases are reported separately | Known device-unavailable exit is `BLOCKED`; assertion failure is `FAIL` | L1 | UI case evidence and infrastructure reason |
| HQ-08 | Acceptance/Gherkin traceability | Every AC links to passing executable test IDs; Given/When/Then is preserved | Missing, unknown, failed, or skipped linked test prevents AC pass | L1 + L2 | AC-to-test IDs and traceable issue |
| HQ-09 | LCOV coverage | Independently worked line/function/branch totals match the report | Zero hits, partial hits, malformed evidence, and escaping source paths are rejected or reported honestly | L1 | Raw LCOV, numerator/denominator, exact percentages |
| HQ-10 | Native DevEco coverage | `coverageReport.json` line/function/branch totals match an independent calculation | Zero, partial, ignored functions/branches, malformed report, and missing executable lines are handled honestly | L1 + L2 | Native JSON, exact percentages, uncovered lines |
| HQ-11 | Changed/module/full scope | Each scope includes only its selected production evidence | Unchanged files, other modules, tests, generated files, and build output are excluded | L1 + L3 | Selected files/lines and excluded-file assertions |
| HQ-12 | ArkTS linter normalization | Code-smell and bug records retain rule, severity, file, line, and remediation | Unsupported format or out-of-scope issue cannot silently enter the report | L1 | Normalized issue and source evidence |
| HQ-13 | Architecture rules | A forbidden import in the configured source layer creates one traceable issue | Allowed import or file outside the source layer creates no issue | L1 + L3 | Rule ID and source line |
| HQ-14 | Reliability smells | Empty catch creates a critical reliability issue | A handled catch and generated/test copies do not create the issue | L1 + L3 | Issue category/severity and source line |
| HQ-15 | Function size | Function over the configured line limit fails its rule | Function at or below the exact boundary passes | L1 | Function start/end and issue count |
| HQ-16 | Cyclomatic complexity | Independently counted decisions produce the exact complexity and threshold result | Value at threshold passes; value above threshold fails | L1 + L3 | Function evidence and worked decision count |
| HQ-17 | Maximum nesting | Independently nested blocks produce the exact depth and issue | Depth at threshold passes; deeper code fails | L1 | Function evidence and expected depth |
| HQ-18 | Duplication | Cross-file repeated block produces an exact deduplicated line percentage | Same-file repetition, short/non-contiguous text, generated/tests, and overlapping windows do not inflate it | L1 + L3 | Duplicate groups, lines, denominator, percentage |
| HQ-19 | CRAP | Known complexity/coverage pairs match `CC^2 * (1-C)^3 + CC` | Missing coverage yields unknown, not zero; lower coverage raises CRAP for the same function | L1 + L2 | Independent formula inputs and exact result |
| HQ-20 | Mutation strength | A behavior-sensitive test kills a real ArkTS mutant | Weak/unrelated test lets it survive; compile error is excluded; timeout blocks; zero valid mutants is unknown | L1 + L2 | Operator, source line, test exit, denominator, score |
| HQ-21 | Source isolation | Mutation copy preserves dependencies and leaves original production hashes unchanged | A test that writes source cannot escape the isolated copy; relative symlinks remain valid | L1 + L3 | Before/after hashes and isolated path |
| HQ-22 | Deterministic scores | Functionality, reliability, maintainability, test-quality, and overall values match independent formulas | Missing categories are renormalized, not fabricated; penalties clamp to 0..100 | L1 + L2 | Score inputs, weights, formula, result |
| HQ-23 | Quality gates | Metric, score, and filtered issue-count gates pass at the boundary | Below/above threshold fails; missing required input blocks; every operator is covered | L1 + L2 | Comparator expression, status, evidence IDs |
| HQ-24 | Reports and automation contract | Terminal, JSON, and Markdown agree and order is stable | Invalid config exits 4; internal failure exits 5; no score/gate lacks evidence | L1 + L3 | Exit code, report hashes, cross-format assertions |
| HQ-25 | Offline package execution | Packed CLI installs in an isolated prefix and reproduces source-run results without network | Package excludes tests/temp/cache and cannot depend on the source checkout | L3 | Pack file list/SHA, installed binary path, semantic report diff |

## Real Scenarios

1. **Existing multi-module negative baseline:** run a real 18-module Harmony
   project with its current weak tests. Expected: build and unit command pass,
   native coverage is zero, selected mutants survive, and configured gates fail.
2. **Controlled positive requirement:** add a pure ArkTS decision to an isolated
   project copy and cover every branch with real Hypium assertions. Expected:
   native coverage matches the DevEco report, the selected mutant is killed,
   CRAP is low, AC is linked, and quality gates pass.
3. **Controlled weak-test variant:** keep the same production requirement but
   remove the boundary assertion. Expected: at least one mutant survives and
   the mutation gate fails; coverage may remain high, proving coverage alone is
   insufficient.
4. **Existing single-module compatibility project:** initialize and analyze an
   unrelated Harmony repository without changing its source. Expected: one
   module is discovered, unsupported commands stay unresolved, and static
   findings/report paths remain deterministic.

## Completion Rule

A capability is not accepted because a report field exists. It is accepted only
when the expected value or state is independently known, the opposite behavior
is detected, and the report links the result to concrete command, test, metric,
issue, file, and line evidence where applicable.
