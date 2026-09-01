# Verification Results

## Candidate

- Date: 2026-08-27
- Tool tests: 58 passed, 0 failed
- Host Spec Superflow tests: 479 passed, 0 failed
- Real projects: one 18-module project and one unrelated single-module project
- Controlled requirement: identical ArkTS production code with strong and weak Hypium tests
- External evidence bundle: `/tmp/harmony-quality-verification-final`

`PASS` means both the expected value and an opposite or boundary behavior were
proved. `PARTIAL` identifies a real environment boundary rather than treating a
fixture as a device result.

## Scenario Results

| Scenario | Expected | Actual | Result |
|---|---|---|---|
| Strong tests, changed scope | Build/test/AC pass, 100% changed-line coverage, mutant killed, CRAP 2 | All matched; overall 100; all three gates passed | PASS |
| Weak tests, same production code | Coverage can stay high but behavior mutant survives | Line coverage 100%, mutation 0%; mutation gate failed; exit 2 | PASS |
| Existing 18-module project | Honest baseline, no invented success | Build/unit pass; coverage 0%; 2 mutants survived; complexity 18; CRAP 342; gates failed | PASS |
| Existing single-module project | Discover module without inventing commands | `entry` discovered; build/test/lint/UI remained `unresolved` | PASS |
| Mutated real Hypium run | A failed assertion must not pass because Hvigor exits 0 | Native result reported 1 failure; CLI classifies it as failure/killed | PASS |
| Repair-oriented report | Every actionable issue must locate the code and every failed gate must explain the target | Issue and project stack frames open exact VS Code file/line/column links; failed gates show current, target, and remediation | PASS |

## Score Sensitivity

The following runs use the same real Harmony project, score configuration, and
quality gates. The code variants retain the same passing strong test suite.

| Variant | Functionality | Reliability | Maintainability | Test quality | Overall | Why it changed |
|---|---:|---:|---:|---:|---:|---|
| Strong baseline | 100 | 100 | 100 | 100 | 100 | Covered decision, killed mutant, no findings |
| Weak tests, unchanged production | 100 | 100 | 100 | 50 | 90 | Coverage remains 100%, but the mutant survives |
| Empty catch and uncovered fallback | 100 | 75 | 100 | 64.29 | 86.61 | One critical reliability issue, line coverage 28.57%, CRAP 6 |
| Untested multi-branch function | 100 | 100 | 90 | 38.1 | 85.62 | Branch coverage 0%, line coverage 14.29%, complexity 4, CRAP 20 |

Both production-code variants build successfully, execute two passing Hypium
tests, kill the selected mutant, and leave the original source hashes unchanged.
The failed status is caused by the affected coverage/CRAP gates, not compilation
or test infrastructure.

## Capability Results

| ID | Result | How the positive path was proved | How the negative/boundary path was proved |
|---|---|---|---|
| HQ-01 Module discovery | PASS | Fixtures and real projects returned stable 18-module and 1-module lists | Empty project fails; generated/dependency trees excluded |
| HQ-02 Command discovery | PASS | Executable wrapper advertising tasks generated argv commands | Missing, unverified, and partial multi-module commands remain unresolved |
| HQ-03 Safe argv/paths | PASS | Project paths with spaces and macOS symlink aliases execute | Evidence, Hypium, report, and analysis path escapes fail |
| HQ-04 Init lifecycle | PASS | First init and `--force` generate deterministic config | Repeat preserves developer edits and reports `ALREADY_CONFIGURED` |
| HQ-05 Build | PASS | Real Hvigor build and fixture build pass | Non-zero build fails; missing command and timeout block |
| HQ-06 Unit tests | PASS | Real Hypium case names and summary are parsed | Non-zero and exit-0 assertion failures fail; stale/missing result blocks |
| HQ-07 UI/system tests | PARTIAL | Configured UI result is parsed separately in process-level tests | Device-unavailable blocks and assertion failure fails; no local device target was available for real E2E |
| HQ-08 AC traceability | PASS | Real AC-1 links to the exact Hypium case and preserves Given/When/Then | Missing, unknown, failed, and skipped linked tests prevent AC pass |
| HQ-09 LCOV | PASS | Worked line/function/branch fixture matches independent totals | Zero/partial hits and malformed/path-escape evidence are covered |
| HQ-10 DevEco coverage | PASS | Real `coverageReport.json` gives exact 100% and 0% cases | Malformed documents, missing lines, ignored entries, and path aliases are covered |
| HQ-11 Analysis scopes | PASS | Changed, module, and full tests select their intended source | Other modules, unchanged lines, tests, generated code, and dependencies are excluded |
| HQ-12 ArkTS lint normalization | PASS | Fixture retains rule, severity, file, line, and remediation | Unsupported format and out-of-scope evidence fail or are excluded; real project had no verified linter producer |
| HQ-13 Architecture | PASS | Forbidden import emits a source-linked issue | Allowed import and source outside configured layer remain clean |
| HQ-14 Reliability smells | PASS | Empty catch emits a critical reliability issue | Handled catch and generated/test copies do not emit it |
| HQ-15 Function size | PASS | Above-limit function emits exact start/end evidence | Exact threshold and below pass |
| HQ-16 Complexity | PASS | Independent decision count matches reported complexity | Exact threshold passes; one above fails; real maximum is 18 |
| HQ-17 Nesting | PASS | Independent nested fixture matches reported depth | Exact threshold passes; deeper code fails |
| HQ-18 Duplication | PASS | Cross-file repeated block gives exact deduplicated percentage | Same-file, short, generated, test, and overlapping windows do not inflate it |
| HQ-19 CRAP | PASS | Independent formula matches real strong value 2 and real baseline 342 | Missing coverage is unknown; lower coverage increases CRAP |
| HQ-20 Mutation | PASS | Strong real Hypium test kills strict-equality mutant | Weak test survives; compile error excluded; timeout/baseline failure block |
| HQ-21 Mutation isolation | PASS | Dependencies/symlinks preserved and source hashes unchanged | Source-writing command stays in copy; original/copy production manifests have zero diff |
| HQ-22 Scores | PASS | Independent non-perfect fixture matches all category and overall formulas | Missing categories renormalize; penalties clamp to 0..100 |
| HQ-23 Gates | PASS | Metric, score, and issue gates pass at exact boundary | All six operators, missing required input, and weak mutation failure covered |
| HQ-24 Reports/exit contract | PASS | Terminal, JSON, and Markdown agree and deterministic report bytes match | Invalid config exits 4; internal report I/O failure exits 5 |
| HQ-25 Offline package | PASS | Exact tgz installs with `npm --offline`; installed CLI reproduces source semantics | Package has no tests, caches, dependencies, or source-checkout reliance |
| HQ-26 Repair navigation | PASS | Real uncovered lines and failed Hypium project frames emit exact local VS Code links | External/dependency frames remain in JSON but do not obscure Markdown repair links |

## Commands and Evidence

```bash
# Tool and host regression
npm test

# Strong/weak real requirement
node bin/harmony-quality.mjs check --project <strong> --scope changed --base HEAD
node bin/harmony-quality.mjs check --project <weak> --scope changed --base HEAD

# Package and offline install
npm pack --json --pack-destination <pack-dir>
npm install --offline --prefix <prefix> --ignore-scripts --no-audit --no-fund <tgz>
<prefix>/node_modules/.bin/harmony-quality check --project <strong> --scope changed --base HEAD
```

Evidence files include source and installed reports, strong/weak/18-module
reports, RED/GREEN logs, native failed Hypium output, package manifest, SHA-256,
and before/after production-source manifests. The production manifest diff is
zero bytes.

## Remaining Environment Boundaries

- A real UI/device run remains pending until an emulator or device appears in
  `hdc list targets`; fixture evidence does not replace it.
- The tested real repositories did not expose a verified SDK ArkTS-linter task.
  Normalization and quality behavior are proved, but a project-specific linter
  command must be configured when one exists.
