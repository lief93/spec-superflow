# Implementation findings

## Current architecture findings, 2026-09-14

The sole active queue is task_plan.md. Entries below this section are historical
observations, not an inventory of current unsupported features. In particular,
transitive serialized inline loading and typed UI modules have since progressed.

- The old plan mixed accepted increments with obsolete Next action and worker
  instructions. It is archived in docs/execution-history-20260914.md.
- Current source audit: docs/backend-reuse-audit.md. Declaration consumers and
  their latest evidence: docs/declaration-call-contract.md.
- FunctionBodies is the borrowed official-body contract. BinaryBodies resolves
  a bounded serialized JVM-inline graph; LibraryInlining uses official inlining.
  There is no general KLIB-body loader or ordinary JVM-bytecode translator here.
- R2.1 now distinguishes source/serialized origins and precise unavailable-body
  reasons; inline diagnostics consume the provider result. A checked target
  replacement is not a Kotlin body. Actual signature-only and replacement tests
  prove that distinction. See docs/binary-bodies.md for evidence and R2.2 gaps.
- R2.2 method-generic members can reuse the same official registration and
  inliner as top-level generic functions. The new failure was in our backend's
  source-owner query, not a missing Kotlin generic substitution algorithm:
  binary provenance must not qualify as an input source class/module.
- The separate KLIB proof reuses official loadIr/JsIrLinker to obtain actual
  non-inline bodies, then reuses the ETS backend's typed tree and module emitter.
  Official moduleFragmentToUniqueName is only an optional JS output-name map;
  actual module ownership must follow resolver/library descriptor identity.
  Public KLIB session/phase/runtime integration remains separate and unfinished.
- Member extension/default binding was already present in the official common
  inliner and our registered signature types. The missing integration was a
  blanket guard, not a missing substitution algorithm. Actual serialized
  generic extension bodies now pass both IR identity and JVM/ETS-host checks.
- Dependent (`T : R`) and non-null (`T : Any`) binary method bounds also compose
  through the existing official InlinerTypeRemapper. New exact-input tests
  establish coverage instead of adding a second upper-bound/substitution engine.
- Class property overriding already has authoritative official accessor bodies
  and override edges. The missing work was ETS storage/dispatch and target
  identity: generated getter/setter declarations can share a source span, while
  base/derived backing fields must remain separate. Reuse official `overrides`
  and preserve accessors; do not inline open property reads into field reads.
- Target abstract accessors must participate in concrete implementation checks
  by kind. A derived getter masks a parent's setter in ETS/JS, so resolving each
  half independently through ancestors can falsely accept an incomplete override.
- Next inherited-default work must separate the inherited default provider from
  the eventual virtual implementation. Common default factories already walk
  override graphs; JS stubs/injectors additionally depend on JS undefined and
  super-context intrinsics, so copying the whole JS stage is not direct ETS reuse.

## Historical observations

- BinaryBodies.kt currently inventories inline calls in application files and
  registers owners from that inventory per binary facade. This does not establish
  general reachable serialized inline/helper dependency loading.
- Official JvmIrDeserializerImpl and the common inliner are already integrated
  for the documented serialized file-facade subset. Ordinary JAR signatures are
  not function bodies; generic/member and unresolved helper paths remain bounded.
- Shared interfaces are in docs/shared-contracts.md. UI already lowers to the
  shared EtsProgram. Do not rebuild UiTextModule or another expression parser.
- The previous simple native fixture is a regression oracle, not a specification
  from which to infer arbitrary Kotlin or Compose semantics.
- Pinned Kotlin/JS/common source references are indexed in
  docs/kotlin-js-backend-reference.md and the existing official source archive.
  Prefer actual upstream passes/implementations over handwritten string rules.
- Workspace is extensively dirty and tools/ is currently untracked relative to
  HEAD. Do not stage all files, revert work or use branch status as proof of ownership.
- R1 target contract: non-generic class/interface heritage, abstract signatures,
  canonical member/override identities and explicit super delegation use shared
  nodes; independent target tests are green. Source lowering is worker-owned.
- ComposeLowering currently places reactive fields and all builder methods in one
  entry component with a shared `this`. Splitting these methods into arbitrary
  physical files would change capture/state ownership. R1 safely preserves
  ordinary helper file ownership and exposes page --out-dir; fully independent
  source-component emission remains an explicit R1 follow-up, not a claimed fix.
## R1 integration boundary

The public quantifier fixture exposed a language boundary missed by the isolated
runtime oracle: the official IR for `value ?: -99` includes an EQEQ against null.
The current primitive equality rule did not accept it. Keep the original fixture
and implement the literal-null path through resolved identities; do not generalize
arbitrary object equality to target reference equality. Evidence:
tests/stdlib/.build/quantifiers.G4dqSP (failed before target output).

The remaining source-UI file ownership work must distinguish stateless source
builders from methods that read entry-owned state or require captured slot
bridges. Physical file movement without a checked owner/call/slot relation is not
an acceptable fix. Plan this as a separate R1 follow-up after current integration
acceptance, not as a filename rewrite or another text-emission path.

## R2B discovered boundary

Bounded receiver probe-ofQifv advanced past generic member lookup but encountered
unsupported official `kotlin.internal.ir.EQEQEQ` for source-object `===`. Preserve
the failed fixture/IR and keep general equality in R3. The bounded receiver batch
tests returned-object aliasing by mutating the original and observing the returned
alias, not by claiming source referential equality is supported. No equality rule
or per-page workaround is added for this test.

Public binary extension replay public-2r2zwH separately proves the loader/inliner
success does not imply printable target code: official
IR_TEMPORARY_VARIABLE_FOR_INLINED_EXTENSION_RECEIVER carries the compiler name
`this`. Existing language temporary naming only recognized IR_TEMPORARY_VARIABLE
and special names. Normalize this official generated origin using the existing
symbol-keyed temporary allocator, while preserving source names and the target
reserved-word validator. This is language lowering, not an adapter or UI fix.

After that origin fix, public-vETIRJ generated output exposed a source binding
legality gap: `arguments` is legal Kotlin and a legal target property name, but
not a strict-mode value binding such as a constructor parameter. Target RED
RzbdoE accepted it incorrectly. Target GREEN LujaDm separates value binding
validation from member names. Language binding repair must remain symbol-based
and collision-safe, retain the property name/source span, and rename only the
illegal parameter/local binding. Do not weaken validation or rename the fixture.

## R2C generic signatures and defaults

Generic overrides carry separate method type-parameter symbols even when their
printed names coincide. Official IrOverrideChecker checks their arity and bounds
using positional symbol correspondence via IrTypeSystemContextWithAdditionalAxioms.
Language reuses official makeTypeParameterSubstitutionMap after owner substitution;
target hierarchy comparison uses its own typed signature contract. Only bound
method parameters correspond: free class identities and canonical member IDs must
remain exact. JS ABI bridge emission is not needed for this bounded same-name ETS
subset. Plain-class generic methods were already supported; baseline-ZfFfBk
retains that control and the actual hierarchy failures.

The nongeneric call type-argument guard previously covered source references but
not source-owned member calls. Target RED r8u7lt reproduced that gap. Extending
the ownership check retains external stdlib signatures that intentionally arrive
already instantiated, without letting source methods claim generic arguments.

Default expression extraction already uses official IrDeclarationDeserializer and
FunctionInlining. Current BinaryBodies traverses all declared defaults, whereas
the official inliner expands only omitted defaults at a call site. Missing an
unused default's dependency is conservatively rejected by the current symbol-only
body contract. R2C tests this boundary explicitly; call-sensitive dependency
selection is deferred, not implemented by dropping unresolved references.

## R2E declaration identities

Cross-file top-level overload groups must follow Kotlin package visibility, not
only IrFile ownership. Private-only groups remain file-local; mixed private/public
overloads in one file connect to visible sibling overloads. Official NameTable
still keys allocations by declaration, while target calls/imports retain source
IDs. The corrected current fixture passes 15 ordinary and five private-scope
JVM/module cases (r2e-green-Nl91IP); flat duplicate private names and cross-package
import aliases remain unsupported boundaries.

Actual member inlining introduces IR_TEMPORARY_VARIABLE_FOR_INLINED_PARAMETER
with local name `this`, just as extension inlining previously introduced its own
receiver origin. Target replay-szE9s7 demonstrated the reserved binding failure.
LanguageLowering now routes only that generated receiver binding through its
existing symbol-keyed allocator. Replay-lgYLzV proves three JVM/host outcomes and
receiver/argument/callback effects with explicit external receiver type mappings.
Loading actual inline bodies does not supply an implementation of a binary class.

## R2E review composition and R2F official inventory

- Fixed review is now an active gate. R2E passed its third review after composing
  private visibility with source inline, same-package imports and overloads.
  Synthetic accessors use official KlibSyntheticAccessorGenerator plus the
  official type/value remappers; omitted slots are retained because the shared
  generator's receiverAndArgs filters nulls. Accessor names use official JS
  NameTable keyed and ordered by real helper identities, not synthetic spans.
- R2F reads pinned Kotlin 2.1.20 sources under
  `/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/org/jetbrains/kotlin`.
  Common `LocalDeclarationsLowering` owns capture analysis, constructor/call
  rewriting and capture fields. `LocalClassPopupLowering` moves local non-inner
  classes to their nearest declaration container after that rewrite. Moving a
  declaration alone cannot establish capture semantics.
- JS `StaticMembersLowering` moves nested declarations to the source file and
  records `originalFqName`, but requires JsCommonBackendContext and JS export
  behavior. Its complete phase cannot be plugged into the current JVM-backed
  context unchanged; ETS must retain source identity before any ownership move.
- Official capture fields have the exact synthetic origin
  LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE. Their
  initializer writes precede constructor delegation and use the exact
  STATEMENT_ORIGIN_INITIALIZER_OF_FIELD_FOR_CAPTURED_VALUE. Current ETS class
  lowering accepts source properties, not these raw fields, and requires leading
  delegation. Do not broadly relax constructor ordering or raw-field acceptance.
- Current EtsClass identity incorporates its emitted name, unlike EtsFunction's
  separate sourceName. The next shared contract must separate source class
  identity/name/scope from emitted names/file placement. Existing documentation
  about nested generic types does not prove lexical nested-class support.
- Subsequent R2F implemented the sourceName class-identity contract and official
  local/static placement, then passed independent review. R2G's consumer now
  accepts the exact official value-capture fields and constructor prefix for
  eligible local classes; it does not accept arbitrary raw fields or derived
  constructor prefix writes. Earlier inventory bullets above describe the
  pre-implementation state, not the current feature set.
- R2G review shows synthetic parameter safety must include emitted overload
  bindings, not just source constructor parameters. Reserving source spellings
  only misses official NameTable-generated function names. The same existing
  overload/class naming services must supply those emitted bindings.
