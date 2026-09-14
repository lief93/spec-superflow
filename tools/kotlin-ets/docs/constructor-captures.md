# Capture and native construction phase composition

## Contract and official reuse

The pinned Kotlin 2.1.20 JS phase list places local declarations, local-class
popup and inner-class lowering before constructor conversion. The ETS frontend
now follows that prerequisite after inlining. It directly reuses common
SharedVariablesLowering, LocalDeclarationsLowering, LocalClassPopupLowering and
the three InnerClasses passes; it does not implement another capture analyzer.

The ETS constructor passes consume the resulting explicit capture/outer
arguments. A shared root selector reads the resolved delegating constructor
symbol, allowing official initialization writes before super delegation. A
source secondary root remains non-primary; existing identity registration tells
the target consumer which constructor performs native allocation. This-delegating
factories cannot contain initialization-prefix writes. Field, receiver, argument,
type and write-count checks remain in the language consumer.

The common local lowering's VisibilityPolicy hook retains source constructor
visibility instead of assigning its default private visibility to every local
constructor. Actual private source roots remain private. Official parameter
origins also drive existing JS NameTable collision handling in copied factories;
user parameter names win over generated capture names.

## Supported composition

- Named local Any-only classes with one allocation root and secondary chains,
  including no-primary roots, shared mutable captures and private primary roots.
- Named nongeneric Any-only inner classes/chains with one allocation root,
  including secondary chains and original no-primary roots. Outer identity stays
  shared, rather than copying its current fields into the constructed object.
- Local declarations in field/init bodies are lifted before native multi-entry
  construction duplicates initializer bodies. Initializers still run once.
- Multi-entry local construction when captures are needed only during
  construction. Official common lowering passes those as parameters without
  retaining captured fields, so the existing dispatcher consumes them directly.

Multiple roots with stored captured fields or inner outer links remain explicit
diagnostics. Generic inner binders, captured inheritance, anonymous owners and
local/inner inherited-default providers are not newly supported. These remaining
composition requirements stay in R2, not silently deferred to page adaptation.

## Verification

From the repository root:

```sh
node tools/kotlin-ets/tests/constructors/captures/run.mjs
node tools/kotlin-ets/tests/constructors/run.mjs
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/local-classes/captures/run.mjs
KOTLIN_ETS_BUILD_SLOT=1 node tools/kotlin-ets/tests/inner-classes/chains/run.mjs
node tools/kotlin-ets/tests/inner-classes/core/run.mjs
bash tools/kotlin-ets/tests/target/run.sh
```

Capture run-EnPet9 passes 40 flat and 40 cross-file Kotlin/JVM versus ETS-host
results, strict host types and reversed-input module determinism. Inputs include
Int limits, shared/independent instances, effect order, default arguments and
source names colliding with generated capture parameters. Actual lowered IR
checks four stored captures, constructor-only captures, two outer bindings,
two non-primary native roots, seven factories and removal of a required capture
write. The malformed IR is rejected; calls may not target removed constructors.
Flat SHA-256: e056b75216866e9c87d7c2e423ead9204b422ac43d89e9fef4637111fc4b43a6.

Earlier RED evidence found the initializer-popup prerequisite, common local
constructor visibility and copied-factory capture-name collision. Intermediate
run-Aw1rxB also exposed an incorrect test assumption: official lowering stores
only captures read after construction, not every captured constructor argument.
The final test checks that optimization explicitly, not an invented field count.

Constructor regression run-j80b1A passes 90 flat and 90 module results, six
former-negative positive inputs, four precise refusal boundaries and the existing
eighteen factory/seven secondary-root/eight dispatcher identity proof. All 80
input hashes match. Flat SHA-256:
497d2c38f363f07b8288ef5ec53946d41ce2ba526c1555ff12f402f2b02773fa.
Earlier run-OvgjRQ exposed a stale count that treated the class-owned inherited
default helper as a constructor factory. The assertion now checks both kinds
separately. run-LcKUIU reached the old initializer fixture's next boundary:
`kotlin.run` has no loaded inline body. That original input remains a precise
missing-body rejection, while the new init-block fixture proves local popup and
single initialization without relying on that absent dependency.

Local capture regression green-yMMZ1X passes 30 JVM results in both output forms,
six captured classes and eight malformed-IR refusals. Inner-chain green-LU6ynq
passes 20 JVM/flat/module results, strict host types, deterministic modules,
immediate ancestor bindings and seven remaining exclusions. The unchanged old
Secondary input now passes native-root/outer-binding and target type checks;
the excluded behavior was not merely removed from the test list.

Core run-iuktB1 passes official field/prefix/call ownership, the former secondary
factory positive and three remaining source-structure exclusions. Target suite
b4JdhD passes constructor control flow, member visibility and all existing
inheritance/generic/binding/UI target contracts. Main self-check and whitespace
validation pass; no separate reviewer was used.

These are host and compiler-IR checks, not ArkTS SDK, device or UI acceptance.
The combined R2 SDK/native gate remains pending.
