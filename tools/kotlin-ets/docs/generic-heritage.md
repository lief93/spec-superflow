# Invariant generic heritage

R2A implements source class/interface heritage with invariant type arguments.
Classes may extend one source class and implement source interfaces; interfaces
may extend source interfaces. Parents can be concrete (`Forward<Int>`) or depend
on the child's parameter (`Storage<U>`, `Storage<List<V>>`). Methods in a heritage
hierarchy remain non-generic, but their signatures may use class parameters.
Ordinary generic source functions can call these methods through an interface.

## Official reuse

The pinned official Kotlin 2.1.20 source cache is
`/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`.

- `org/jetbrains/kotlin/ir/util/IrTypeUtils.kt:189-223` implements immediate
  supertype substitution and `getAllSubstitutedSupertypes`. The official example
  composes `C<Z> -> B<List<Z>> -> A<List<List<Z>>>`. Language lowering calls this
  utility directly, rather than implementing a second ancestor traversal.
- `org/jetbrains/kotlin/ir/types/IrTypeSubstitutor.kt:27-112` implements recursive
  type substitution, nullability merging and symbol-keyed parameter binding.
  Language lowering uses `IrTypeSubstitutor` to apply the actual receiver's
  arguments to the official ancestor types and to compare original override
  signatures. IrTypes are compared before target mapping; different Kotlin
  numeric types cannot become valid overrides just because ETS uses `number`.
- `org/jetbrains/kotlin/ir/util/IrFakeOverrideUtils.kt:38-88` implements
  `collectRealOverrides` with real-declaration filtering. This existing direct
  reuse supplies canonical emitted member IDs, not copied fake-override IDs.
- `org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/JsClassGenerator.kt:317`
  binds generated members through `realOverrideTarget` and emits real bodies.
  This is reference architecture only: JS prototype/default-interface emission
  and name mangling are not reused for ETS, nor is JS text an intermediary.

For an inherited member, the actual receiver is viewed as the declaring class
through the official substituted ancestor set. Identical diamond paths agree;
missing or incompatible instantiations are rejected rather than choosing the
first path. The valid Kotlin frontend independently rejects incompatible
diamond arguments; the source fixture retains that negative.

## Target contract

No new target nodes or fields are needed. `EtsClass.typeParameters` also applies
to interfaces. `baseClass` and `interfaces` keep their declaration `symbolId`
and complete argument lists. The leading `EtsSuperConstructorCall.baseClass`
is the exact instantiated direct parent and preserves the original arguments
and their evaluation order.

`EtsMember.symbolId` and `EtsFunction.overrides` identify real declarations.
The call-site member type is instantiated for the actual receiver. The target
validator, owned by main, validates heritage/member/constructor signatures and
bounds using edge substitutions and invariant argument matching. Raw class-ID
matching is insufficient and is not a language-side fallback.

## Boundaries

No variance, reified expansion, generic inherited methods, default interface
bodies, super member calls, overloads or nested-class expansion. Existing
inherited property/accessor dispatch rejection remains explicit; a base-typed
read of its own declared property is distinct and already supported. Constructor
forwarding does not introduce new constructors or permit use of `this` during
inherited initialization. Upper-bound receiver dispatch is not expanded.

## Tests and migration

`tests/inheritance/generic/GenericHeritage.kt` contains concrete and parameterized
parents, multi-edge inheritance, nested arguments, interface diamonds, abstract
generic parents, virtual dispatch and constructor-side-effect cases. Its
`GenericBase<T>`/`GenericChild : GenericBase<Int>(3)` is the exact former negative
shape from `tests/inheritance/UnsupportedGeneric.kt`; `migratedGeneric()` adds
observable base-typed property parity. After the public positive suite passed,
main renamed the old fixture to `tests/inheritance/SupportedGeneric.kt` and
added an explicit positive check to the existing inheritance runner. No negative
was silently skipped. The updated old suite is rerunning under main.

Approved serial commands, once the integration owner grants a build slot:

```sh
node tests/inheritance/generic/probe.mjs
node tests/inheritance/generic/run.mjs
```

The probe retains original IR, official ancestor types, canonical member
bindings, detached target validation and complete emitted ETS. The public CLI
runner compares 31 results with the same original Kotlin input on JVM, preserves
four source-linked unsupported boundaries, and checks incompatible diamond
rejection in both JVM and the CLI frontend. Both retain hashes and command/error
logs under `.work/`, use low-CPU SerialGC options and must run serially.

The pre-edit source snapshot for genuine initial RED is
`/tmp/kotlin-ets-generic-heritage-baseline-CI4UE5/src`. Set
`KOTLIN_ETS_SOURCE_ROOT` to that path when running `probe.mjs` to reproduce the
prior generic-heritage rejection without changing repository source.

## Focused evidence

Frozen-baseline RED: `tests/inheritance/generic/.work/probe-ilgZ7L/result.json`.
The original input compiles to actual Kotlin IR, then the old producer rejects
`Generic inheritance is not supported`. No source input rewrite is used.

Current GREEN: `tests/inheritance/generic/.work/probe-C78GPn/result.json`.
This proves six actual inherited call bindings, official composed ancestor
types, interface type parameter identities, concrete and parameterized parents,
compatible diamond paths, exact direct super constructor types and detached
target validation. `actual.ir`, `official-supertypes.txt` and `bindings.txt`
retain the original compiler evidence. The full production input hash guard
passed; no source changes were needed during this focused execution.

```text
5172048822700b609ceaabb12815e9f0def17b2f4e4091a7c71f21258d5dd949  src/language/LanguageLowering.kt
e393cfb4e062a50b95d5bc7a99bb8f206d5cf99945ca356c8b38c787f798a340  src/target/Validator.kt (main-owned dependency)
0f5b9bacf9972f66df5ec1e884dc26f8eef39de3c78730ba64fecc2c1cd386da  tests/inheritance/generic/GenericHeritage.kt
a0734b609028c4a9e28cdba013c93262da359702b7d5e2556bb7ac264da69d30  probe-C78GPn/GenericHeritage.ets
```

## Public integration evidence

Main reported GREEN `tests/inheritance/generic/.work/run-NTzuJo/result.json`:
31 same-input Kotlin/JVM versus public-CLI-generated host results, four
source-linked unsupported cases, and incompatible-diamond rejection by both
JVM and the CLI frontend. Its complete generated output SHA-256 is
`a0734b609028c4a9e28cdba013c93262da359702b7d5e2556bb7ac264da69d30`,
exactly matching focused `probe-C78GPn/GenericHeritage.ets`.

Only after this public proof did main migrate the former generic negative to
the explicit positive check described above. The old inheritance suite rerun
is still pending; this document does not claim its result in advance.
Actual SDK/native acceptance remains pending with main and is distinct from
host parity. Language production remains frozen; no source/test edits or
compiler runs accompanied this documentation-only evidence update.
