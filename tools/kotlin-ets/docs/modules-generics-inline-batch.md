# Modules, Generics and Source Inlining

2026-09-13. Three architectural lanes developed in parallel against the same
official Kotlin 2.1.20 frontend and typed ETS tree. This is a bounded backend
increment, not general Kotlin or Compose migration completion. No independent
review, commit or push was performed.

Follow-up: [local-declarations.md](local-declarations.md) records the subsequent
official local-function/shared-capture lowering. The local-function rejection
below describes this earlier batch and its SDK-discovered boundary.

## Delivered Scope

| Lane | Implemented | Not implied |
| --- | --- | --- |
| Official lowering | Source-library body acquisition through explicit frontend inputs; official callable-reference preparation, function inlining and returnable-block normalization | Binary JAR/KLIB body loading or the complete Kotlin/JS lowering pipeline |
| Generic types | Non-reified invariant functions, simple generic classes, member/accessor/call-site substitution with binder identities | Local function declarations, full variance, star projections, reified runtime types, inheritance, overloads |
| Module output | `--out-dir`, flat source filenames, declaration-ID imports including types, per-file runtime closure, output refusal on unsupported input or collisions | Complete binary module ABI, package collision renaming, page-mode multi-file conversion |

Kotlin/JS is the concrete reference. Common inline transformations are directly
invoked from the pinned official compiler. ETS generic types, validation and
module text are ETS-specific implementations using resolved official symbols,
not alternate Kotlin parsers. See [library-inlining.md](library-inlining.md),
[generics.md](generics.md) and [module-output.md](module-output.md).

The main lane owns module assembly and combined SDK verification; the other two
lanes own official source inlining and generics. The shared node traversal is
also used by runtime dependency collection. No screenshot-specific cases or new
Compose control mappings were introduced.

## Verification

Evidence paths below `tests/` are relative to `tools/kotlin-ets/`. Commands ran
from the repository root. Generated ETS was not manually edited.

| Check | Observed result | Evidence |
| --- | --- | --- |
| `node tools/kotlin-ets/tests/modules/run.mjs` | 12 JVM/target cases, including cross-file generic class/function cycles; type/function imports, helper closure, overwrite/collision/no-partial-output checks | `tests/modules/.work/run-Zwgo1x/result.json` |
| Combined module/inline SDK build | Six unchanged generated `.ets` modules compile; compiler-input records, ABC and HAP verified; backend and source hashes equal module-generation hashes | `/private/tmp/kotlin-ets-modules-sdk-grYH7v/manifest.json` |
| Generic contract | Eight grouped JVM/target results, four unsupported-source boundaries, 17 malformed-target rejections; final source hashes frozen | `tests/generics/.work/sdk-fix-final-BI3gvc/manifest.json` and `freeze.json` |
| Official inline CLI/IR | Four JVM/target results agree; ten official inline blocks, zero residual source-inline calls/returnable blocks; binary-only dependency correctly rejected with no output | `tests/inline/.work/run-5qGbSX/` |
| Official concat normalization | Six JVM/target results and actual common-pass evidence pass after inline stage | `tests/lowering/.work/run-N22j1Z/` |
| Typed language contract | Source symbols, defaults, typed adapters, statement/value distinction and negative source locations pass | `tests/language/.work/typed-0Jyasx/` |
| Target tree/printer | Existing target contract and printer checks pass | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-target-tests.0KQLqu` |
| Backend separation | Lowering without printer, immutable deterministic printing and ten differential cases pass after the local-function rejection | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-backend-tests.r7eXNv` |
| Language regression | Five positive and eight source-linked negative fixtures pass | `tests/language/.work/run-S14ktv/` |
| Property accessors | Eighteen JVM/target results pass | `tests/language/.work/accessors-z0YN2C/` |
| CLI integration | Three tests pass, including unresolved frontend/no target | `python3 -B tools/kotlin-ets/tests/integration/test_cli.py`, 29.291 seconds |
| Runtime traversal | 26 node paths and five function kinds still pass after sharing the traversal | `tests/stdlib/.build/runtime-tree.ZeAlXA/` |
| Standard library regression | 66 JVM/target results; real symbol acceptance and malformed IR/target rejection pass | `tests/stdlib/.build/cli.08Mzjd/` and `/tmp/kotlin-ets-stdlib-symbols-followup-20260913-KqDdTv.log` |
| Existing language SDK regression | Seven newly generated language/accessor/concat modules compile as ETS; unchanged source, backend and target hashes | `/private/tmp/kotlin-ets-language-sdk-H3t1Ah/manifest.json` |
| Final Compose interface regression | Eleven accepted, thirteen rejected, helper differential and complete typed-boundary checks pass after the local-function rejection | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-ui-tests-LgxUO4/` |

The backend reflection test now permits the explicit `symbolId` metadata field
and additionally checks that source-class type IDs refer to actual declarations.
It still rejects arbitrary raw-code payload fields and leaked compiler objects.
The UI boundary test similarly compares the model type with the real source
class declaration identity instead of the earlier name-only type value.

At closeout, all 20 production Kotlin files still match both final SDK manifests.
The two SDK builds account for six integrated modules plus seven existing language
modules. No SDK failure was cleared by editing generated output. Independent
review remains paused and no commit/push or device/page acceptance was performed.

### SDK-discovered Boundary

An expanded local-generic fixture passed host execution but failed actual ETS
SDK compilation: `arkts-no-nested-funcs` at `Functions.ets:41`. Evidence is retained
in `/private/tmp/kotlin-ets-modules-sdk-Sitncv/`. The installed SDK also declares
`arkts-no-generic-lambdas`; simply printing a generic arrow is not a supported fix.

Local function declarations are now rejected with source locations before output,
and nested `EtsFunction` nodes are rejected by target validation. The unchanged
`locally/keep` source remains a negative fixture, rather than being silently removed
from coverage. Full function lifting/capture conversion is deferred. This corrects
an earlier support claim; it is not successful local-generic translation.
Ordinary lambdas and official-inliner blocks still pass the final regression.
No generated ETS was patched to make the SDK build pass.

Differential execution means Kotlin/JVM versus generated target executed through
the installed DevEco TypeScript host toolchain. Actual ETS SDK compilation is
separate evidence. There is no claim of ArkVM execution, device installation or
visual/page equivalence in this architecture batch.

## Remaining Work

1. Acquire/link real binary IR dependency bodies in a coherent compiler universe.
   A compiled JVM signature is not an IR body. The source-library route is an
   implemented alternative, not completion of that task.
2. Extend language and type coverage through shared lowering and validation:
   local function lifting/capture conversion, inheritance/interfaces/overloads,
   broader generics and control flow.
3. Extend standard-library/runtime semantics with independent Kotlin oracles.
   General `for`/range/inline stdlib support is not supplied merely by adding an
   inliner for explicitly supplied source bodies.
4. Move the remaining Compose text envelope onto the same typed target model.
   No page-specific fallback should substitute for those backend capabilities.
