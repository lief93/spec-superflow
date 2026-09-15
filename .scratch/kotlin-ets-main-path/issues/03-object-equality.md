# Object and data-class equality

Status: accepted (ordinary source objects and supported data properties)
Scope: spec L2; L3-L8 stay queued
Review: deferred by user

Reuse official FIR/IR generated data-class bodies and the existing typed language
consumer. Reference Kotlin/JS EqualityAndComparisonCallsTransformer: distinguish
referential equality, literal-null checks and resolved equals dispatch. Do not
replace data-class equality with JSON or generic recursive object comparison.

Verify public CLI output against JVM for identity, distinct equal/unequal source
objects, user equals/hashCode, generated constructor-property equality, nullable
and nested supported properties, cross-file calls and stable identity hashes.
Hash numbers for identity objects need not equal JVM's process-specific values.
Generated structural hashes must agree and equal objects must have equal hashes.
Array identity versus data-class array-member hashing needs separate coverage.

## Implementation and evidence

- The official generated data-class function bodies now flow through the ordinary
  language consumer. Constructor properties, null guards and nested source calls
  are not reconstructed from names or reflected object fields.
- EqualityRules consumes resolved EQEQ/EQEQEQ symbols and real override links.
  Nullable operands evaluate once, including the right operand when the left is
  null. Default source-object equals is identity; overrides remain source calls.
- Default source-object hash is cached per instance, following Kotlin/JS's lazy
  identity-hash strategy. Structural hashes use the JVM oracle for Int, Boolean,
  Char, String, Float/Double, nested source values and IntArray data members.
  IntArray equality remains referential, not deep equality.
- RED `equality/.work/run-0Vf1JT` (EQEQEQ), `run-gbtWba` (nullable field hash),
  `run-osh0ne` (explicit Any.equals), `run-IS7pci` (floating formatting boundary),
  and `run-2BWjTc` (generated floating structural equality) are retained.
- Final `equality/.work/run-hdA83L`: 15 flat + 15 multi-file JVM/ETS outcomes,
  strict host type checks, reversed-input determinism and input/output hashes.
- Existing model regression `models/.work/run-euEkay`: all 70 flat/module
  results still match. This preceded removal of an unused compareTo branch;
  the final equality run does not contain that unrelated expansion.
- Final SDK `/private/tmp/kotlin-ets-equality-sdk-fjqX5t`: all three unchanged
  generated modules appear in CompileArkTS inputs; ABC/HAP artifacts produced.
  Earlier SDK `/private/tmp/kotlin-ets-equality-sdk-maHdvw` is retained too.
  No native execution or
  device parity is claimed. No generated ETS was manually changed.

Limits: floating data-class auto-toString remains unsupported (the fixture
explicitly supplies a source toString). This is not a formatting completion claim.
Dynamic erased numeric distinctions belong to L4, collection representations
and equality composition to L5; unsupported value families remain diagnostics.
Independent review remains deferred, not passed.
