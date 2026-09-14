# Parallel Backend Batch

Historical checkpoint for the preceding batch. The next batch is recorded in
[modules-generics-inline-batch.md](modules-generics-inline-batch.md).

2026-09-13. This is a bounded implementation batch, not completion of the Kotlin
backend roadmap. Development and tests continue; independent review is paused by
the user's instruction. No commit, push, release or device/page acceptance is
claimed.

## Architectural Work

| Area | Delivered in this batch | Still open |
| --- | --- | --- |
| Compiler pipeline | Actual Kotlin 2.1.20 common string-concatenation pass runs between official FIR2IR and ETS lowering | General library-body loading/linking, inlining and the remaining reusable passes |
| Types and declarations | Custom member getters/setters on simple classes/objects, preserving backing-field and accessor semantics | Generic declarations, inheritance/interfaces, overloads, nested classes, delegated/extension properties |
| Runtime dependencies | Language-mode runtime selection from typed symbol references, including transitive helper dependencies | Wider stdlib/Long/Float semantics and dependency loading, not implemented by runtime selection |
| ETS output | Native accessor syntax; unused helpers omitted from language modules | Multi-file output, module ownership/import/export assembly and wider target validation |
| Compose adapter | Existing interface regression only; no new page-specific rules | Complete typed UI tree and shared dependency collection for page mode |

The compiler and runtime work ran in separate ownership lanes; the main
development lane implemented accessors and integrated the tests. They share the
existing typed expression/body interface. Neither the UI adapter nor runtime
selection gained a Kotlin parser or a second expression-lowering engine.

## Reuse Classification

- **Direct official implementation:** `FlattenStringConcatenationLowering` is
  loaded from the pinned compiler JAR. A real official JVM context supplies the
  current frontend's builtins/symbols/providers. No JVM phase chain or JS text
  intermediate is executed. See [official-lowering.md](official-lowering.md).
- **ETS-specific lowering using resolved official IR:** properties retain native
  getter/setter syntax. Their bodies use the shared language lowerer; property
  access and backing-field access remain distinct. Official property passes are
  references, not copied or invoked implementations. See
  [property-accessors.md](property-accessors.md).
- **Official architecture adapted to the existing ETS tree:** runtime selection
  follows symbol references and dependency closure. It does not execute Kotlin/JS
  DCE or load arbitrary library bodies. See
  [runtime-dependencies.md](runtime-dependencies.md).

## Verification Evidence

Commands run from the repository root. Evidence directories retain commands,
outputs and results; test-generated ETS was not manually corrected.

| Check | Result | Evidence |
| --- | --- | --- |
| `node tools/kotlin-ets/tests/lowering/run.mjs` | Six JVM/generated-target comparisons; 25 plus calls to zero; 75 declaration records retained; effectful custom `toString` ordered correctly | `tests/lowering/.work/run-WHHFKk` |
| `node tools/kotlin-ets/tests/language/accessors.mjs` | Eighteen JVM/generated-target comparisons, including compound assignment and post-increment | `tests/language/.work/accessors-rgrnnc` |
| `bash tools/kotlin-ets/tests/target/run.sh` | Accessor shape/type rejection and existing printer/target checks pass | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-target-tests.RrC0qR` |
| `node tools/kotlin-ets/tests/language/run.mjs` | Five positive and eight negative CLI fixtures pass | `tests/language/.work/run-O2OYtC` |
| `node tools/kotlin-ets/tests/language/typed.mjs` | Symbol/default/adapter result/statement-effect checks pass | `tests/language/.work/typed-RTf5os` |
| `bash tools/kotlin-ets/tests/backend/run.sh` | Lowering without printer, immutable printing, source binding and ten differential cases pass | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-backend-tests.DOyx4m` |
| `python3 -B tools/kotlin-ets/tests/integration/test_cli.py` | Three CLI contract tests pass | Test runner output: 3 tests, 37.615 seconds |
| Runtime selection CLI/tree plus existing stdlib tests | Five selection cases, 26 traversal paths, all five function kinds, 71 actual-IR calls and 66 differential cases pass | `tests/stdlib/.build/runtime-final.iAF4DH/freeze.json` and its linked results |
| `node tools/kotlin-ets/tests/language/sdk.mjs` | Seven freshly generated language modules compile as ETS; source and generated-byte hashes unchanged | `/private/tmp/kotlin-ets-language-sdk-t327mU/manifest.json` |
| `node tools/kotlin-ets/tests/stdlib/check-sdk.mjs` | Scalars/Lists compile with only their required helper subsets | `/tmp/kotlin-ets-stdlib-sdk-ahNn0T/result.json` |
| `node tools/kotlin-ets/tests/ui/run.mjs` | Eleven accepted and thirteen rejected page-mode CLI cases, helper oracle and typed UI boundary pass | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-ui-tests-0qC5r0` |

Differential execution uses Kotlin/JVM versus the generated target executed by
the installed DevEco TypeScript toolchain on the host. Actual ArkTS compilation
is separately verified by SDK compiler-input records and produced bytecode/HAP.
This batch does not claim device execution, visual equality or page migration.

One existing UI negative-case assertion changed because official normalization
replaces `Typography.toString()` with a string-concatenation operand. It remains
unsupported, produces no target, and now reports the operand's type and exact
`typography` source token. The test asserts the specific new diagnostic and
source slice, not a relaxed acceptance condition. No production UI special case
was added.

## Next Architectural Boundary

The next compiler task is to establish a tested library-body loading/linking and
inline boundary, not add per-page `repeat`/`let` substitutions. A resolved JVM
signature is not an available IR body. In parallel, generic declarations and
module ownership need explicit typed contracts before expanding their emitters.
The current single-file CLI and transitional UI text envelope remain explicit
limitations; neither is hidden behind a successful SDK build.
