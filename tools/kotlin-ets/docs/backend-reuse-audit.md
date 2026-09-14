# Backend reuse audit

2026-09-14, source inspection at `44fb21a`. This is an architectural inventory,
not a new behavior test or a claim that removing a guard makes a feature work.
No production changes were made. No subagents were used.

## Already reused

`src/core/Frontend.kt:82` invokes source/library inlining, local declarations,
for-loop lowering, flattened string concatenation and expected nullability.

- `LibraryInlining.kt:69`: official callable-reference conversion and
  `FunctionInlining`; synthetic accessor generation also reuses official code.
- `LocalDeclarations.kt:87`: official shared-variable, local-declaration, local
  popup and three inner-class passes. R2I extended consumers, not capture analysis.
- `ForLoops.kt:29`: official common ForLoopsLowering with an ETS-oriented context.
- `OfficialLowerings.kt:19`: common string-concatenation flattening.
- `Backend.kt:28`: compiler IR becomes a compiler-independent typed target tree,
  then the target validator runs. There is no JSON round-trip in this main chain.

Thus this is not a handwritten Kotlin parser. Reuse is real but is selective:
`createJvmLoweringContext` supplies JVM-backed services, not a complete JS backend
context with its intrinsics, runtime symbols, exports and phase prerequisites.

## Gaps by common cause

| Priority | Common cause | Concrete evidence | Correct implementation boundary |
| --- | --- | --- | --- |
| P0 | Declaration normalization and target consumption are incomplete | LanguageLowering.kt:251 rejects top-level stored properties; :515 rejects covariance; :520 rejects default interface bodies; :606 permits only interface method signatures; :615 requires one primary constructor; OverloadNaming.kt:94 rejects virtual overloads | One declaration/call contract covering storage, dispatch, constructors and identity; reuse applicable official passes and consume their results in ETS. Not a separate adapter for each method name. |
| P0 | Dependency body availability is narrower than the language front end | BinaryBodies.kt:143 only accepts inline binary bodies; :145 requires serialized IR; :196 rejects non-inline transitive calls; :199 rejects constructors; :221 rejects generic members | Establish body loading/linking and target-replacement policy for a reachable dependency graph. A signature-only JAR is not an IR body. Never remove these gates without providing missing bodies and target support. |
| P1 | Standard-library algorithms and target primitives are mixed | StandardLibraryRules.kt:180/:223 map filter/map to custom helpers; :298 limits map receivers to finite list signatures; StandardLibraryDependencies.kt contains a finite runtime-type inventory | Separate reusable algorithm bodies from runtime protocols/intrinsics. First connect one coherent collection dependency family; avoid perpetuating one handwritten algorithm per public API. Numeric representation differences still need ETS implementations. |
| P1 | Real target/runtime semantics are missing | LanguageLowering.kt:450 rejects runtime interface discrimination; :978 rejects reified/variant parameters; Tree.kt has EtsThrow but no try/catch/finally node | Type metadata, exceptions and runtime representation need explicit target support. Official lowering alone does not implement these in ETS. |
| P1 | Framework semantics need target-specific structure | ComposeLowering and AdapterModules delegate slots/modifiers to scoped typed services | Keep platform adapters, but reuse ordinary expressions, parameter binding and target validation. State, slots and modifiers are not only call-name replacements. |

The priorities above describe architectural dependencies, not incident counts.
Not every line containing `unsupported` is a missing feature: checks for forged
synthetic origins, unbound symbols, wrong constructor identities or invalid types
are correctness guards and must remain.

## Official reference versus plug-in reuse

Inspected cached official sources under
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources/`, especially
`org/jetbrains/kotlin/ir/backend/js/JsLoweringPhases.kt`:

- Lines 503-521: default argument generation, override patching, injection and cleanup.
- Lines 531-532: common PropertiesLowering.
- Lines 572-584: JS bridges and type-operator lowering.
- Lines 594-601: secondary-constructor and factory conversion.
- Lines 451-472: suspend transformation and continuation stages.

These demonstrate organized compiler phases, not proof that every JS phase can
run unchanged on our context. DefaultArgumentStubGenerator is a common reference;
its JS specialization, bridges and secondary constructor factories have backend
dependencies that must be inspected before selection. Common PropertiesLowering
may also erase property syntax we can preserve directly in ETS. Do not blindly
run every lowering merely to increase the number of reused classes.

## Next implementation order

1. Fix a declaration/call normalization contract using existing typed nodes where
   possible: defaults, property access, dispatch and constructor forms. For each
   official candidate record inputs, generated nodes, context/runtime dependencies,
   ETS consumer and name-preservation policy. Do not resume generic-member-only
   gate removal as the main architectural task.
2. Implement a coherent declaration family through that contract and verify
   composition cases, not only isolated syntax. Keep source/target structural and
   behavior tests together. Required generated bridges must be traceable.
3. Establish dependency-body/linking strategy and prove a standard-library family
   without source-spelling replacements. Separate source bodies, serialized IR,
   unavailable bodies and explicit target implementations. KLIB loading remains
   a separate unimplemented path, not something the current JAR reader provides.
4. Add target/runtime semantics required by the selected families; framework APIs
   use that same backend. Broader UI integration follows these contracts.

The practical goal is an ETS backend with reusable language machinery, not a
larger set of page exceptions or an unverified wholesale transplant of Kotlin/JS.
