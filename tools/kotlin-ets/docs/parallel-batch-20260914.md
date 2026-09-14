# Parallel architecture batch, 2026-09-14

Baseline: [shared contracts](shared-contracts.md). Implementation only; independent
review and commit/push remain paused. No page-specific patches or device runs.

| Lane | Bounded implementation | Status |
| --- | --- | --- |
| Frontend/dependencies | Real serialized binary IR body availability and official loading/linking experiment | Experiment complete; binary loader not integrated; precise diagnostics implemented |
| Language | Official Int progression for-loop lowering, target control-flow preservation, source/JVM differential | Frozen; 38 differential cases and actual IR contract pass |
| Standard library/runtime | Typed filter/filterNot; two resolved progression intrinsics needed by the official loop pass | Frozen; filter, progression and runtime contracts pass |
| ETS output | Per-file declaration names, exported value/type dependency checks, import-collision preflight | Frozen; contract, 24 module cases and actual module SDK compilation pass |

Write boundaries: frontend worker owns Frontend/LibraryInlining and binary-body
tests; language worker owns LanguageLowering and ForLoops (main wires its phase);
stdlib worker owns stdlib/runtimes and their tests; main owns target/output,
Backend and integration harness updates. Shared interfaces have one owner.

Each lane inspects the actual pinned Kotlin 2.1.20 compiler/runtime sources. A
failed experiment is recorded as unsupported, not replaced by inferred source or
a signature-only body. Generated JS is never an input to the ETS backend.

Main freezes production after workers finish and reruns contract, public CLI,
JVM/host differential and actual ETS SDK compilation against the combined tree.
Pre-freeze worker results do not establish combined implementation stability.

## Bounded results

- [Binary bodies](binary-bodies.md): real serialized IR was deserialized and bound,
  but official inlining failed at missing `fileEntry` identity. No fabricated
  body/file or signature-based replacement was integrated. Source-library
  inlining remains available.
- [Loops](loops.md): Int `..`, `until`, `downTo` and supported direct `step` forms;
  official loop normalization, scope preservation, deferred closure captures,
  break/continue and empty/extreme ranges. Not general List/array/Long iteration.
- [Collections](collection-filter.md): bounded array-backed `filter/filterNot`,
  plus two resolved official progression intrinsics. Ten runtime helpers are
  inventoried and emitted through the existing dependency contract.
- [Modules](module-output.md): same local names in different files are legal;
  cross-file values/types require exports; import conflicts are diagnosed at
  source. Single-file collisions still fail. Kotlin visibility policy and the
  complete typed UI tree are not implemented by this change.

## Frozen lane evidence

Paths below are relative to `tools/kotlin-ets` unless absolute.

| Check | Evidence | Result |
| --- | --- | --- |
| Binary metadata/source fallback | `tests/binary-bodies/.work/policy-4wlkjH` | Pass; binary body use rejected, explicit source fallback verified |
| Actual binary inlining experiment | `tests/binary-bodies/.work/experiment-7kxJ6i/linked-inline.log` | Expected failure; missing source-file identity |
| Loops JVM/host differential | `tests/loops/.work/run-bnPdSl` | 38 same-input cases; 3 source-linked negative cases |
| Official loop IR and typed target | `tests/loops/.work/typed-QnjnrG` | 12 iterator nodes eliminated; 8 typed condition snapshots |
| Filter behavior | `tests/stdlib/.build/filter.HsKDqB/result.json` | 34 cases plus fresh-result checks |
| Progression runtime | `tests/stdlib/.build/loop-adapters.tc18rD/result.json` | 1,300 direct runtime comparisons; 22 JVM/CLI cases |
| Module contract | `tests/modules/.work/contract-yvdqKY` | Namespace/export/import preflight passed |

## Combined verification

Final serial module, SDK, shared-backend and existing UI code-generation
regressions pass. Production stayed frozen throughout these accepted runs.
A pre-freeze module run (`run-5Wuzsy`) passed behavior
checks but correctly failed its compiler hash guard after the final loop fix;
it is not accepted. A subsequent run (`run-iZg4i4`) timed out during CLI build.
The initial SDK run (`/private/tmp/kotlin-ets-language-sdk-qv3Haw`) also timed out
during generation and is not a successful SDK compilation. No timeout or source
stability assertion was weakened. UI/inline concurrent runs were stopped before
serial verification; those interrupted runs are not recorded as passing.
The first serial module retry (`run-M28Upn`) also timed out. Final runs use
`JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'` and one heavy
verification process at a time, without changing compiler semantics or test
timeouts.

| Final check | Evidence | Result |
| --- | --- | --- |
| Modules, JVM/host and negative CLI cases | `tests/modules/.work/run-iZLpGN` | 24 cases; source/implementation hash guards pass |
| Official inline and source-library CLI | `tests/inline/.work/run-T4TKmI` | Pass; binary-only negative remains explicit |
| Module ETS SDK | `/private/tmp/kotlin-ets-modules-sdk-mBta1l/manifest.json` | 7 generated modules; unchanged bytes; ABC and HAP produced |
| Language ETS SDK | `/private/tmp/kotlin-ets-language-sdk-X9fjBy/manifest.json` | 11 generated modules including Loops/Filter; unchanged bytes; ABC and HAP produced |
| Backend without printer; printed JVM/host differential | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-backend-tests.eeXckS` | Pass; input hash stability checked |
| Shared typed language contract | `tests/language/.work/typed-tALgCY` | Pass; value/effect boundary, defaults, rule precedence, frontend lifetime |
| Existing Compose code-generation regression | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-ui-tests-u5HFvk` | Pass; helper JVM/host oracle, renamed input, slots, modifier order, explicit unsupported cases |

SDK compilation is not ArkVM execution, device interaction or visual equivalence.
JVM/host comparisons execute the generated language code in the host oracle;
they do not claim native runtime acceptance. No review, commit or push performed.

## Remaining architecture work

This is one bounded parallel increment, not completion of all four lanes.

1. Dependencies: safe binary-body file/symbol identity and linking; broader real
   project dependency loading and explicit translated/replaced ownership.
2. Language: general iterators, arrays and Long progressions; inheritance,
   interfaces, overloads, local classes and broader generic/exception semantics.
3. Standard library/runtime: coverage beyond the documented bounded collection,
   string and numeric contracts; arbitrary iterator and structural-mutation
   semantics must not be inferred from the array-backed helpers.
4. Target/output: complete typed UI nodes replacing `UiTextModule`; broader
   target legality and Kotlin visibility/export policy. Module checks do not
   constitute that UI-tree migration.
