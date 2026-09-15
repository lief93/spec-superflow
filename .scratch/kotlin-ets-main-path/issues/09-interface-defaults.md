# Interface default implementations

Status: focused acceptance passed
Scope: L8 simple source interfaces and explicit resolved default calls
Review: deferred

Reuse official resolved override identities, shared function-body lowering,
source class dispatch and typed target functions. The target interface retains
signatures; one helper owns each default body and implementing methods forward.
Do not duplicate language parsing or use method names to select an implementation.
Reference Kotlin/JS jsAstUtils super-interface calls and BridgesConstruction
resolveFakeOverride provider selection.

## Implementation

One source-linked helper owns each default body. It goes through the ordinary
function/statement/expression lowerer with an explicit typed receiver. Interface
signatures and implementing methods preserve source method and parameter names.
Necessary helper names use __etsDefault plus owner/method, not numeric renaming.
Inherited class implementations are reused, not re-emitted in every subclass.
Interface-typed virtual calls remain dynamic; explicit qualified calls target
the resolved provider. Default getters and Unit-returning mutations are covered.

## Evidence

- RED defaults/.work/run-bkdt2e: source-linked default-body refusal.
- defaults/.work/run-eU03Ga: six composed JVM/flat/module results, strict types,
  deterministic file order, hashes and method/parameter/bridge assertions.
- /private/tmp/kotlin-ets-defaults-sdk-FSVYN9: three unchanged generated modules
  through actual CompileArkTS, with ABC/HAP. Not native execution.
- Composition includes top-level initialized Map with data-class keys, enum
  results, nullable lookup failure/catch, source super and interface dispatch.

## Boundaries

Simple source interface owners are covered. Generic interface owners with default
bodies explicitly reject; complex generic/default combinations remain excluded by
the approved spec. No whole Kotlin/JS runtime or JVM DefaultImpls phase is claimed
as directly reused. The reused inputs are official symbols/override resolution
and the existing shared ETS language pipeline.
