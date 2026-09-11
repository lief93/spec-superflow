# Source Value Methods

The page pipeline preserves a bounded subset of ordinary Kotlin value methods.
No adapter registration or extra command flag is required. This is separate from
the selected-scene UI projection; it does not reconstruct the whole page's state
machine or external business effects.

For example, this source:

```kotlin
data class Person(val name: String, val active: Boolean)
fun title(person: Person): String = if (person.active) person.name else "Inactive"
// In a composable:
Text(title(Person("Ada", true)))
```

produces a `Person` class and an ordinary `title(person: Person): string` function.
The generated Text calls `title(new Person(...))`; it does not merely display a
precomputed string. Functions remain in their source-named, flattened ETS files,
with imports between files. Names are escaped only as required by ArkTS.

## Supported Boundary

- Reached top-level, unannotated functions with String, Boolean, Int, Double,
  Unit, nullable types and homogeneous List/Array signatures.
- Plain primary-constructor records, nested record fields and constructor
  defaults. `val` fields remain readonly. Classes with bodies, inheritance,
  generic parameters or hidden constructor behavior are not treated as records.
- Parameters, pure calls, local val/var, local assignment, property reads,
  string interpolation, if, explicit-else when, collection for loops and repeat.
- Int addition/subtraction wrap to 32 bits; multiplication uses Math.imul.
  Unsupported arithmetic, including integer division, remains diagnostic.
- Native text and supported numeric style consumers accept generated method
  results. A successfully mapped resource adapter still takes precedence.
- Supported reusable UI parameters remain parameters inside value-method calls;
  two calls with different inputs do not reuse the first preview's literal.

This is not an arbitrary Kotlin-to-ArkTS compiler. Member/extension methods,
coroutines, services, mutable external effects, recursive methods, ambiguous
overloads, Long/Float precision, data-class equality/copy, nullable member access,
and unsupported operations retain a specific diagnostic and the existing marked
preview fallback. A supported nullable signature does not imply all nullable
operations are implemented. Generic record element types may also require a
future type-resolution extension. Domain callbacks and root UI parameter/state
reconstruction are not completed by this increment.
Local functions and local records are not lifted into top-level declarations.
Target intrinsic or normalized-name conflicts fail closed with a diagnostic;
generated import and Builder aliases avoid source value declaration names.

## Evidence and Refresh

`version_json.json` carries `meta.migration.sourceProgram` and per-node
`source.method_references`. The backend never reopens Android source or executes
the project's adapters. The ArkUI manifest's
`source_organization.value_methods` lists emitted declarations, their source and
output files, actual consumers and unsupported expressions. Unconsumed methods
are not evidence of restored behavior. Source-stage fallback diagnostics can
still exist even when a target method is emitted; inspect the consumer evidence
alongside the selected-scene diagnostics.

Regenerate source-page and Lanhu/version JSON to pick up this capability. An
unchanged compatible project contract/snapshot can be reused, but old version
JSON contains neither method bodies nor record declarations. Run the normal
page command through generation, SDK build, installation and same-state visual
comparison; do not modify generated ETS or JSON by hand.
