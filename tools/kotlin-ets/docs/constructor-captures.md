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

Multiple roots with stored captured fields or inner outer links use the checked
common prefix described below. Constructor-only local captures may also be
forwarded through source inheritance: the official generated field set decides
whether pre-super storage is required. Stored captures in named local derived
classes use the bounded heritage contract below. Generic inner binders, inner
classes with non-Any heritage and anonymous owners remain unsupported. Local/inner default
provider composition is documented separately in inherited-defaults.md. Remaining
initialization work stays in R2, not silently deferred to page adaptation.

## Multi-entry stored captures

Common LocalDeclarationsLowering already writes captured fields at every native
super root. InnerClassesLowering similarly initializes its outer link only at
roots, not at this-delegating constructors. The ETS constructor phase consumes
those exact fields and parameters; it follows resolved delegation symbols and
parameter arguments to bind the this-delegating entries and official default
stubs. It does not infer captures from names, source strings or field types.

Every root must have one complete official prefix. Every delegated capture must
be an unchanged official parameter of the caller, with the exact field type and
constructor owner. Only after all entries validate are their field writes moved
to the dispatcher's single prefix. Default argument bodies, source initializers
and secondary bodies still use the existing common injection/inlining machinery.

Shared capture parameters are passed once to the native dispatcher, not repeated
in every nullable entry slot. Inner registration is rebound to that exact native
constructor/outer parameter, preserving the original field and immediate outer
class identities. Each source factory evaluates the outer receiver once; source
fields are not copied or made public. The target consumer retains prefix count,
owner, field and parameter checks, and permits the verified dispatcher branch in
place of the unique-root direct Any delegation. No target validator bypass or raw
ETS node is introduced.

## Stored captures with source heritage

Official common LocalDeclarationsLowering still determines captured field,
parameter and receiver identities, writes them at super roots in argument order,
and leaves this-delegating entries without a second prefix. The ETS backend does
not replace this analysis or rewrite the source IR prefix.

For a named local derived class, the target consumer emits those checked writes
immediately after each native super call, before the derived initializers. It
first inspects source ancestors using official getAllSuperclasses and the existing
inherited-initialization visitor. Ancestor constructor bodies must be available.
Own final stored fields/default getters and generated capture/outer links may be
read; arbitrary methods, virtual/custom getters and escaping this are rejected.
Super-call arguments retain the strict no-this-before-super check. The target
constructor-flow validator still checks every path; it is not bypassed.

This is a deliberately conservative observation boundary, not general effect
analysis. A base callback may update a shared captured cell through its explicit
constructor argument, but must not obtain the not-yet-initialized derived this.
Exact own stored reads also permit an initialized constructor property to feed
another source field. No virtual accessor is replaced with a stored read.

Generated capture field names reserve ancestor capture names and both ancestor
and descendant source member names through existing JS NameTable allocation.
User fields/methods keep their names and visibility. Multiple native entries,
default constructors, shared cells and inherited default helpers use this same
consumer rather than separate capture representations.

Frozen capture run-B1ru9k passes 60 flat + 60 module JVM/ETS-host results, strict
host types, three-file reversed-input determinism and all 62 input hashes. Its
IR/target probe checks one capture in each of StoredBase/StoredChild, two in
StoredEntries, retained pre-super official prefixes, and immediate post-super
typed writes on all six native paths. Existing seven malformed-prefix refusals
remain. Four additional JVM-valid source negatives reject transitive virtual
observation, this escape, secondary-constructor observation and a custom getter,
with exact file/positive spans and no emitted ETS. The shared-state trace checks
effects before/during/after super, inherited defaults and source/private capture
name collisions. Flat SHA-256:
0c701f36b6e04eac103c9fda699920c286aaffe6ab52ff5fa4425fcb260d2b10.

RED run-CVhvdv preserves the former blanket capture/heritage rejection.
run-CnnZfK then caught the old guard rejecting an ordinary final-property read
used to initialize a source field. The test was retained, not replaced by a
constant. CustomGetterCapture verifies the new permission cannot admit executable
getters. Earlier green run-L0bDEB predates this stored-read/collision composition.

Constructor regression run-7GLvPv passes 90 flat + 90 module results, eight
unchanged former-negative positives (including CapturedInheritance), three
remaining boundaries and existing native-constructor identity checks. Its flat
SHA remains 497d2c38f363f07b8288ef5ec53946d41ce2ba526c1555ff12f402f2b02773fa.
Local core run-aoxicY checks the original CapturedBase source as a positive and
retains captured-type, generic-inner and observing-ancestor negatives.
Inherited-default regression run-7u6frm retains 65 flat + 65 module results,
three boundaries and twenty-nine exact helper calls; flat SHA remains
1e88798274a28a90584a10f797d502d3150b0b92a3423eaee9ea69f9ab1db28c.
Target suite K3HkGP passes constructor flow (twenty-two refusals), visibility
(twelve refusals), inheritance/generic/binding and UI builder contracts. All four
source suites' frozen inputs remain unchanged. Main self-check and whitespace
checks pass; no separate reviewer was used.
These are host/compiler-IR checks only; SDK/native and whole-R2 acceptance remain
pending.

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

### Stored-capture dispatcher evidence

RED run-KceVe9 executes the extended original JVM fixture but hits the former
single-root inner-class gate. Initial run-5MgGwr passes 50 + 50 host results;
inspection still found redundant capture slots. The final representation removes
those repeated slots. run-L6yEVd passes behavior but fails to compile a new probe
assertion on nullable SourceSpan.file; it is not accepted evidence.

Frozen run-5p3qcZ passes 50 flat + 50 module JVM/ETS-host results, strict types,
reversed-input determinism and all 57 input hashes. IR proof checks two retained
local capture fields, two multi-entry outer links, exact common constructor
parameters, no repeated capture slots, all source call targets, and seven
malformed-prefix refusals. Tests exercise every new native entry, default masks,
shared-cell updates before default evaluation, one-time receiver evaluation and
two levels of outer-object identity across independent instances.
Flat SHA-256: c9acf2494642da6b2e5fe9263fd0acf42f3ab529e8f8cd188d44daac4f874be7.

Constructor regression run-61KOsX passes 90 + 90 results, seven former-negative
positive conversions (now including the unchanged CapturedDispatch source), four
precise exclusions and all 81 frozen hashes. Its flat and six module outputs are
byte-identical to run-j80b1A. CapturedInheritance explicitly preserves the remaining
captured-heritage boundary. Inner regression green-MlqNLI passes 20 results in
both output forms, fourteen malformed bindings and deterministic module output.
Target suite sW4vki passes constructor flow, visibility, inheritance, generic,
binding and UI target contracts. Main self-check and git diff whitespace checks
pass. No independent review, SDK build or device run is claimed for this increment.
