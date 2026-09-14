# Local declarations and shared captures

This increment addresses the SDK-discovered `arkts-no-nested-funcs` gap. It does
not convert local declarations into generic arrows: the installed ETS SDK also
rejects generic arrow functions.

## Phase ownership

```text
Official frontend and source inlining
  -> official SharedVariablesLowering + ETS SharedVariablesManager
  -> official LocalDeclarationsLowering
  -> existing language/type lowering
  -> typed ETS validation and printing
```

`core/LocalDeclarations.kt` invokes the actual Kotlin 2.1.20 compiler classes,
not a reimplementation of their algorithms. The official passes determine which
variables are captured, lift named local declarations, add capture parameters,
remap generic parameters, and rewrite calls and recursion.

The target-specific `SharedVariablesManager` supplies a typed generic cell class
with an initial value and a mutable property. All reads and writes of one
captured variable use the same cell. This includes accesses in native lambdas
and in the enclosing method. Separate enclosing-method invocations allocate
separate cells. No JVM `Ref` dependency or JavaScript `dynamic` is introduced.

The pass selects bodies containing named local declarations. Ordinary
closure-only bodies keep native ETS capture behavior without new cells.
Generated cell declarations are admitted by an exact synthetic-origin identity;
user declarations using the reserved `__ets` prefix are still rejected.

## Target structure

Original outer method names and parameter names are retained. Local functions
must move because of the ETS restriction. For example:

```kotlin
fun <T> localIdentity(value: T): T {
    fun <U> keep(input: U): U = input
    return keep(value)
}
```

The target calls a module-level `localIdentity$keep<T>(value)` from
`localIdentity<T>(value: T)`. The official scope-qualified name distinguishes
locals with identical source names in different methods. This is not a new
preview/render wrapper or a flattening of the local function into its caller.

A class-owned lifted function becomes a static target method. A captured `this`
is an explicit typed argument; it is not an implicit receiver on the static
method. Target validation distinguishes static and instance calls and rejects
residual nested function declarations. Shared-cell fields and lifted arguments
use the same generic substitution and symbol contracts as ordinary classes and
methods.

## Verification

```sh
node tools/kotlin-ets/tests/local-functions/run.mjs
node tools/kotlin-ets/tests/generics/run.mjs
node tools/kotlin-ets/tests/language/sdk.mjs
```

The local-functions harness records source/backend hashes, commands, generated
ETS, before/after official IR, and independent JVM-versus-host-target outputs.
It checks actual loaded compiler classes, original source offsets and symbols,
local declaration removal, lambda identity preservation, and typed cell IR.
Output syntax is inspected structurally for prohibited nested functions and
generic arrows. Public methods and parameter names are also checked.

Behavior cases cover generic locals, recursive captures, shared mutable state,
generic mutable captures, independently escaping closures, nested captures,
class-instance captures, defaults, named-argument evaluation order, and Int
overflow. Negative fixtures check reserved source names and captured variables
without initializers, including source diagnostics and no published output.

The SDK harness regenerates this module alongside the existing language
fixtures and copies its bytes unchanged into a native build host. Actual ETS
compiler input records and HAP/ABC hashes are required. Host execution does not
prove ArkVM execution, and SDK compilation does not prove a device run.

### Evidence from 2026-09-13

Paths below `tests/` are relative to `tools/kotlin-ets/`.

| Check | Result | Evidence |
| --- | --- | --- |
| Original failure | JVM succeeds; public CLI rejects the first local declaration | `tests/local-functions/.work/run-hWrGPn/` |
| Official IR + public CLI | 12 named locals become 12 lifted declarations; one generic cell class, four captured variables; four grouped JVM/target results agree; both negative fixtures reject without output | `tests/local-functions/.work/run-BqHVpI/result.json` |
| Generic local regressions | 12 grouped JVM/target results, including `LocalBox<T>`; three unsupported generic boundaries | `tests/generics/.work/cli-AwV7Jh/` |
| Typed generic/static contracts | Generic identity and capture binding, scope retention, 17 malformed targets rejected; static class-parameter scope rejected | `tests/generics/.work/typed-5yFWnK/` |
| Existing accessors | 18 grouped JVM/target results agree | `tests/language/.work/accessors-CXQ9K7/` |
| Existing standard library | 66 JVM/target cases agree; unknown API rejected without output | `tests/stdlib/.build/cli.M8Wu4w/` |
| Module output | 16 JVM/module results agree; generic class/function cycles, local generic module, imports and output refusal checks | `tests/modules/.work/run-geB8tH/result.json` |
| Official source inline | Actual official inlined IR, JVM/target results and binary-only rejection | `tests/inline/.work/run-mTj820/` |
| Typed adapter boundary | Symbols, defaults, adapter result and effect/value contracts | `tests/language/.work/typed-2bopQd/` |
| Backend separation | Lowering without printer, deterministic printing and JVM/target results | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-backend-tests.lLxEqB/` |
| Existing UI | 11 positive and 13 negative cases plus typed boundary; no unexpected shared-cell boxing | `/var/folders/fj/rrz0bjhx6cq04j7yghy2qkxh0000gn/T/kotlin-ets-ui-tests-tJPnyi/` |
| Actual ETS SDK | Nine freshly generated modules compiled, with actual ETS input records and ABC/HAP output | `/private/tmp/kotlin-ets-language-sdk-BtaxKU/manifest.json` |
| Multi-module ETS SDK | Seven unchanged modules compiled together, including generic/local imports and official inline output | `/private/tmp/kotlin-ets-modules-sdk-BLy3eg/manifest.json` |

All 21 production Kotlin source hashes in the final local behavior run match the
nine-module SDK manifest and the frozen source tree. The generated
`LocalFunctions.ets` hash also matches across both runs. The SDK additionally
includes `LocalGeneric.ets` to validate generic-class-owned static lifting,
not just generic top-level functions. No device execution, independent review,
commit or push was performed in this increment.

## Remaining boundaries

- Captured variables without initializers are rejected; no guessed default.
- Local classes and unsupported standalone function references remain rejected.
- Unrepresentable generics, inheritance, overloads and suspend semantics retain
  their existing source-linked rejection boundaries.
- Binary library-body loading, general iteration, broader standard-library
  coverage and full target UI-tree integration are separate work.

See the current test evidence before claiming a boundary is supported. This
increment is not whole-language or whole-page acceptance.
