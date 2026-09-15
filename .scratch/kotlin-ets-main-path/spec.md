# Kotlin to ETS main-path completion

Status: active
Baseline: c77e580 (2026-09-15)

Approved by the user with "实施" on 2026-09-15. Implement one finite issue at a
time; independent review remains deferred, while tests and self-checks are required.

## Intent

Complete common language blockers without redesigning implemented capabilities.
The official frontend/IR, shared lowering, typed ETS tree, validator, printer and
module output remain the architecture. Compose consumes that architecture.
Once approved, this spec is the capability baseline and its issues are the POC queue;
old round plans and per-feature documents retain historical evidence, not new work.

The acceptance unit for this round is ordinary Kotlin language behavior, not a
particular page. Preserve original method and parameter names and declaration
boundaries where ETS permits; explain and source-link necessary target bridges.
An already runnable page is not a new deliverable for this round.

## Confirmed user decisions

- Complete the selected common language forms and their combinations in ordinary
  functions, classes and cross-file calls. Isolated syntax demos are insufficient.
- Include explicit super member calls and interface default implementations.
- Map keys and Set elements include ordinary objects and data classes, not just
  primitive values. Equality and hashing must compose with collection behavior.
- Exclude complex generics, reflection, coroutines, multithreading and pathological
  cyclic initialization. Unsupported semantics must produce clear diagnostics.
- Defer independent review only. Keep specification confirmation, tests and
  self-checks. Do not start implementation while this spec is awaiting approval.

## Existing capability versus remaining work

Progress after approval: issues 01, 01b and 02 passed focused acceptance. L1
computed/stored accessors and the documented ordinary-language nonconstant file
initialization contract are implemented. L2 ordinary source/data-class equality
has focused acceptance in issue 03. L3 basic enums passed issue 04. L4 nullable
types passed focused acceptance in issue 05. L5 common Map/Set operations passed
issue 06. L6 basic exception flow passed issue 07. L7 explicit super passed issue
08. L8 interface defaults is next.
Compose lifecycle entry and complete platform exception APIs remain distinct work.
The inventory below records the original baseline,
not a claim that implemented accessor work is still missing.

Paths below are relative to `tools/kotlin-ets`. Existing means bounded support,
not arbitrary Kotlin or proof of native parity on this compiler revision.

| Capability | Existing implementation and evidence entry | Remaining classification |
| --- | --- | --- |
| Functions, parameters, defaults, closures | `src/language/LanguageLowering.kt`, `src/core/DefaultArguments.kt`, `tests/backend/run.sh`, `tests/inline/run.mjs` | Existing; do not rebuild. Non-local returns in fallback let are not supported. |
| Classes, member accessors, local declarations | `docs/property-accessors.md`, `docs/constructors.md`, `docs/local-declarations.md` | Existing bounded support; not all inheritance/capture combinations. |
| Conditions and loops | `src/core/ForLoops.kt`, `tests/loops/run.mjs`, `tests/iteration/run.mjs` | Existing official lowering plus ETS consumers; not a new control-flow parser. |
| Constant-initialized top-level storage | `src/language/TopLevelProperties.kt`, `tests/language/globals/run.mjs` | Existing cross-file reads/writes. |
| Top-level computed accessors | Member accessor bodies already lower through LanguageLowering; top-level storage guard rejects them | Wiring gap: emit and call ordinary target accessor functions, no invented storage. Issue 01. |
| Nonconstant file initialization | TopLevelProperties requires IrConst | Missing initialization timing/order/once-only contract. Issue 02; not solved by removing guard. |
| Float/Double common arithmetic | `src/stdlib/FloatingPointRules.kt`, `tests/language/numbers/run.mjs` (67 JVM/host cases) | Implemented; Long, boxed numeric distinctions and complete formatting are separate gaps. |
| Nullable value composition | `src/core/ExpectedNullability.kt`, `tests/nullability/run.mjs` (57 cases), `tests/language/models/run.mjs` (70 cases) | Implemented bounded ?. / ?: / guarded and generic calls. !! failure and broader casts need focused verification before an implementation claim. |
| Runtime is/as/as? | LanguageLowering.typeOperator handles source classes, String, Boolean, Any | Interfaces and boxed numeric discrimination explicitly reject; do not describe all casts as missing. |
| Data class construction/copy | `tests/language/models/Model.kt` and its public CLI runner | Implemented. Generated equals/hashCode explicitly excluded; object equality remains missing. |
| Enums | LanguageLowering.clazz rejects enum kinds; no IrGetEnumValue consumer | Missing basic language/target support. |
| Lists and common operations | StandardLibraryRules, IterationRules, CollectionEmptinessRules, LetRule; models runner | Existing bounded map/filter/iteration/emptiness/ordinary let; Map/Set not implemented. |
| Exceptions | IrThrow/EtsThrow present; no IrTry/EtsTry consumer | Missing try/catch/finally and associated exit behavior. |
| Inheritance and dispatch | `docs/inherited-defaults.md`, `docs/virtual-overloads.md`, `docs/native-constructor-flow.md` | Much already implemented. Explicit super member calls and interface default bodies reject. |
| Compose consumption | `tests/ui/model-composition/run.mjs` | Existing typed Text/branches/callback consumption, public CLI parity and 70 JVM/host results; not native redraw. |

The table separates implemented features, missing consumers, missing behavior,
and missing evidence. A historical unsupported statement is not proof of a current
gap. A passing fixture is not proof of complete feature coverage.

## Requirements and acceptance cases

The cases below are proposed concrete acceptance details for the confirmed scope.
They define outcomes rather than prescribing a new compiler architecture.

### L1. Top-level properties and initialization

- Stored val/var, computed getters/setters and ordinary custom accessors preserve
  reads, writes, visibility, setter parameters and evaluation count. A computed
  property never acquires a cache or invented backing storage.
- Object, collection and function-call initializers preserve once-only execution,
  declaration order, cross-file dependency order and observable first-use timing.
  Importing ETS must not silently execute effects earlier than the source program.
- Initializer failure must not publish apparently initialized default data or
  silently retry effects. General cyclic initialization is outside this round;
  any cycle boundary admitted by the backend must be documented, not approximated.
- Verify repeated getter reads, conditional setters, compound assignment,
  nonconstant initialization through another file, and failure/repeated access.

### L2. Object and data-class equality

- Distinguish identity from structural equality. Ordinary objects without a custom
  equals retain identity semantics; source equals/hashCode overrides participate.
- Data-class generated equals/hashCode follow primary-constructor properties,
  null handling and nested supported values. Do not add unrelated body properties
  or replace Kotlin array/reference behavior with generic deep comparison.
- Verify same instance, distinct equal instances, unequal instances, nulls,
  overridden equality, and equal objects with equal hash codes across files.
  Identity hash numbers need not equal one JVM run's nondeterministic numbers;
  stability and equality/hash contracts must hold.

### L3. Basic enums

- Preserve enum item identity, declared order, ordinary constructor properties and
  methods, parameter/return use, comparisons and when selection.
- Include name/ordinal and common enumeration/lookup (entries or values/valueOf)
  needed to use enums as normal program data; unknown lookup must fail correctly.
- Verify enum values returned from another file and used in equality and Map/Set.
  Per-entry anonymous subclasses and complex generic enum hierarchies are outside
  the basic form in this draft.

### L4. Nullable values and runtime type operations

- Reuse existing ?. / ?: / guarded/generic paths; verify combinations with
  functions, properties, models and collection results instead of rebuilding them.
- Verify !! on null/non-null values, is/!is, as/as? on supported source classes and
  interfaces, and common scalar types through Any. Preserve single evaluation,
  safe-cast null results, throwing-cast failures and applicable catch selection.
- Missing runtime distinctions require an explicit representation or diagnostic,
  not treating every numeric type as interchangeable because ETS uses number.
  Arbitrary erased/reified generic discrimination is outside this round.

### L5. Basic Map/Set with object values

- Support read-only and mutable Map/Set construction, lookup/membership, size,
  insertion/replacement, removal and traversal. Preserve Kotlin distinctions
  between absent keys and present null values, plus documented iteration order.
- Keys/elements include common primitive values, enums, ordinary identity objects,
  custom-equality objects and data classes from other files.
- Verify equal-but-distinct object lookup/removal, deduplication, replacement,
  unequal objects with colliding hashes, null handling and cross-file mutation.
  Hash collisions must not be treated as equality.
- Existing List operations remain regression coverage. Do not claim every
  collection algorithm or stable behavior after mutating a key's equality/hash
  fields while it is stored; that is not a valid portable Kotlin guarantee.

### L6. Basic exception control flow

- Preserve try/catch/finally in statement and result positions, catch ordering,
  propagation, rethrow and finally effects on normal and exceptional exits.
- Include return/break/continue through finally and a finally return/throw
  overriding a pending exit. These are ordinary control flow, not network logic.
- Establish the target exception representation for the supported standard
  exceptions and simple source exception classes used by these cases. Null/cast,
  collection and initializer failures must compose with that representation.
- Compare exception categories, selected handlers and effect traces; identical
  platform stack traces or every JVM-specific message are not required.

### L7. Explicit super member calls

- Call the resolved base implementation, not virtual redispatch to the override.
  Preserve receivers, arguments, return values and evaluation order, including
  supported property accessors. Reuse existing constructor/heritage machinery.
- Verify an override calling super, an inherited call across files, and argument
  effects. Do not rebuild already-supported super constructor delegation.

### L8. Interface default implementations

- Preserve inherited default bodies, implementing-class overrides, calls through
  interface-typed parameters and explicit qualified default calls where Kotlin
  resolves a concrete implementation.
- Verify a single default, inherited defaults, a class override, and explicit
  conflict resolution across files. Let the official frontend reject ambiguous
  invalid Kotlin; never choose an implementation by a simple name match.
- Reuse current symbols, inheritance and dispatch. Complex generic/default-method
  combinations outside the agreed simple forms remain excluded.

## Delivery and dependency order

After approval, begin with computed property wiring (existing draft issue 01),
then complete L1 initialization/storage accessors, L2 equality and L3 enums.
L4 audits existing behavior before adding missing support. L5 consumes the L2/L3
representations. L6 and L4/L1 failure paths share one exception contract; any
required prerequisite runtime slice must be identified in the owning ticket,
not become a second general expression or exception implementation. Complete L7
and L8 through the existing inheritance pipeline.

This is a delivery outline, not permission to implement eight families at once.
Only one finite issue is claimed at a time. Split issues by verifiable dependency
after spec approval, with the reused code, changed consumer and acceptance cases
recorded. Completing issue 01 alone does not complete L1 or this round.

## Round completion gate

1. All L1-L8 common forms have implementation and passing composition evidence;
   already supported portions receive regression checks, not duplicate work.
2. Original Kotlin/JVM and generated flat/multi-file code agree on the same
   inputs: results, mutation/evaluation order and relevant failure behavior.
3. Cross-feature cases include initialized model/enum collections, equal object
   keys from another file, nullable lookups/casts with catch/finally, and default
   interface or super calls returning the same models. Inspect original method
   and parameter names as well as behavior.
4. At the round milestone, unchanged generated modules pass actual ArkTS/SDK
   compilation. Record host and native execution evidence separately; host
   differential results alone cannot establish full ArkVM equivalence. No Compose
   control coverage, page installation or pixel comparison is an acceptance
   substitute for this language round.
5. Unsupported families are documented with source-linked diagnostics. Individual
   issue completion, round acceptance and deferred review remain separate states.

## Acceptance and process

- Every issue identifies reused implementation and the actual missing consumer.
- Use original Kotlin/JVM as the result/effect oracle, flat and module ETS host
  execution, source names/parameters, type checking and source-linked rejections.
- Record input hashes and evidence paths. Never edit generated ETS to pass.
- Keep unsupported semantics explicit; do not replace them with default data/UI.
- No independent review for now, per latest user instruction. Tests and self-check
  remain mandatory; mark review as deferred, not passed. No reviewer dispatch.
- No new language parser, JSON compatibility route, page-specific workaround,
  exhaustive generic closure, or broad coroutine/platform work in this scope.
- SDK/native/visual evidence is separate. Previously runnable pages remain valid
  historical evidence but do not establish new feature behavior.

## Explicit non-goals

Full Kotlin/JVM compatibility; complex generics; reflection; coroutines and
multithreading; pathological cyclic initialization; exhaustive standard-library
coverage; arbitrary external/platform APIs; full Compose/ArkUI control coverage;
page visual fidelity; redesign of the existing compiler architecture.

## Draft history

The computed-property test was started prematurely before spec confirmation.
`tests/language/computed/.work/run-ESPVAQ` reproduced the current top-level accessor
guard and is failed exploration evidence, not an approved acceptance run. No
production compiler change had been made at draft time. Subsequent implementation
and acceptance are recorded in the numbered issues after the user's approval.
