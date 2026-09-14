# Implementation findings

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
