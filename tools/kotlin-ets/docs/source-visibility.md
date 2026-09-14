# Source visibility in language modules

The language backend previously marked every top-level function and class as
exported, including Kotlin `private` declarations. The resolved official IR
visibility now controls the existing typed target `exported` flag.

- File-private functions/classes stay local to their generated ETS file.
- Public declarations remain exported with their original names.
- Kotlin `internal` declarations must be exported between generated ETS files so
  calls and type references within one Kotlin compilation remain valid.
- Imports still follow declaration identities through `emitEtsModules`; this
  change does not infer visibility from names or printed source.

ETS file exports are not a complete implementation of Kotlin module access
control. An external ETS consumer can import an emitted `internal` declaration.
Packaging/API-surface enforcement is not claimed by this increment. Class-member
access control, UI builder ownership and binary-body visibility are separate
contracts, not silently changed here.

The pinned Kotlin 2.1.20 JS implementation makes the same distinction between
public API exports (`export/ExportModelGenerator.kt`, `getExportCandidate`) and
internal cross-module references (`transformers/irToJs/JsIrProgramFragment.kt`,
signature-tag import/export planning). We reuse the official IR visibility
predicate, not the JS export model or its runtime/module representation. The
current ETS `exported` flag is a file-linkage decision, not a claim that both
export layers have already been implemented.

## Verification

The existing owning suite is `node tests/modules/run.mjs` from `tools/kotlin-ets`.
It checks generated export declarations, actual module exports, same-name private
functions in different files, internal class/function imports, a private class
used through an internal function, and original JVM versus generated-module
results. Its existing generic/local-function, collision, no-overwrite and
no-partial-output checks remain mandatory.

An immutable pre-edit compiler snapshot at
`/tmp/kotlin-ets-r2e-baseline-20260914/tools/kotlin-ets` failed the new assertion
`Private source function must remain file-local` in
`tests/modules/.work/run-dgIHDv`. The earlier `run-Z2349x` exposed an invalid test
fixture (a public signature exposing an internal class); the fixture was corrected
before obtaining the intended RED. Neither failure is reported as a passing test.

Final frozen current-tree verification passes in
`tests/modules/.work/run-dQ29nj/result.json`: 28 JVM/generated-module outcomes,
private function/class exports, internal imports, illegal private access,
generic/local-function regression and output safety checks. The separate naming
suite also passes five private-scope module cases in
`tests/modules/overloads/.work/r2e-green-Nl91IP/result.json`.
These are compiler/host checks, not SDK or native execution evidence.

## Independent review: source inline linkage

The first review found a legal combination absent from that initial suite:
an internal inline function calling its file-private helper from another file.
`run-ogu53Q` reproduces the rejected cross-file reference. The source inliner
now uses Kotlin's `KlibSyntheticAccessorGenerator` and
`modifyFunctionAccessExpression` for actual source-owned private calls inside
inlined blocks that crossed a file boundary. The original helper stays private;
only the official synthetic forwarding function is exported for module linkage.
Binary owners, class-private members and arbitrary unresolved calls are not
made public by this pass.

The generated accessor is kept in its original file, cached by official symbol
identity, and follows the common generic-type/value remappers so copied parameter
types and defaults bind to its own declaration. Kotlin's synthetic offsets are
retained; they are not fabricated source lines. Existing import and target type
validation remains enabled. Generic-helper RED `run-teuTTm` exposed the need for
type remapping. `run-LmT7Hn` passes 36 JVM/module cases with the ordinary and
generic bridges. The expanded dependent-default case then exposed a stage
precondition: official `receiverAndArgs()` filters omitted argument slots.
`run-FVvHty` records that failure. The ETS pass preserves all original argument
slots after the official call rewrite because this backend still emits defaults;
the copied defaults also use official `ValueRemapper` for parameter identity.
The expanded owning suite `run-iW7Gqe/result.json` passes all 40 JVM/module
outcomes and the unchanged output/visibility guards. `run-zg9gfK` was a compiler
build attempt missing the utility import, not a semantic result.

Second review found a combination of the two fixes: official accessors for
same-file private overloads share a suggested name and synthetic source span.
`run-KyCcNa` reproduces the existing overload guard rejecting that combination.
Accessors now use the official Kotlin/JS `NameTable` keyed by the original helper
declaration, with allocation ordered by real helper file/offsets. Source bindings
are reserved before allocation; neither synthetic offsets nor the source overload
guard are changed. The new module fixture combines two private overloads and a
user declaration matching the official accessor suggestion.
`run-znizDA/result.json` passes all 44 JVM/module cases and unchanged output
guards; the original collision-named source helper remains private, and both
overload bridges receive distinct bindings without fabricated source offsets.
