# Map and Set value semantics

Status: focused acceptance passed
Scope: spec L5, consumes L2-L4
Review: deferred

Reuse official resolved collection declarations/loop lowering and existing source
equality/hash lowering. Implement ETS collection storage with key equality/hash
callbacks rather than native Map object-identity semantics. Compare original JVM
and flat/module output for cross-file model keys, collisions, enums, nullable
values, insertion order, replacement/removal and mutation through parameters.

Reference: Kotlin v2.1.20 stdlib JS collections InternalHashMap.kt, HashMap.kt,
LinkedHashMap.kt and HashSet.kt. The official implementation separates key hash,
key equality, presence and insertion order; ETS requires its own supported storage
and type boundary. Do not claim direct reuse of the full JS runtime.

## Implementation

- MapSetRules plugs into the existing CallRule and type mapping; source symbols,
  not arbitrary call text, select operations. Key callbacks reuse source
  equals/hashCode consumers; floating keys reuse total comparison and bit hashes.
- Numeric hash buckets retain separate entries for collisions and insertion order.
  Presence is independent of nullable values. Set uses the same map storage.
  Runtime instances and callbacks travel across generated modules structurally.
- Supports mapOf/mutableMapOf/emptyMap and setOf/mutableSetOf/emptySet, get/set/put,
  membership/containsValue, size/isEmpty, remove/clear, direct/destructured iteration.
  Pair factory inputs are evaluated once; read-only Pair widening uses typed fields.
- Common source/data-class, enum, primitive and nullable keys tested. Generic erased
  Any keys, collection views, iterator removal, concrete HashMap constructors and
  full collection algorithms are not claimed. Non-finite literal constants remain
  diagnosed; floating NaN behavior is tested using supported arithmetic.

## Evidence

- RED `tests/language/collections/.work/run-ZQPxB3`: original JVM succeeds;
  previous backend rejects MutableMap at the source location.
- `tests/language/collections/.work/run-mTqIQn`: 12 flat/module JVM/host results,
  strict host type checking, deterministic reversed input and source hashes.
- `/private/tmp/kotlin-ets-collections-sdk-q30EBN`: three unchanged generated
  modules pass actual CompileArkTS with ABC/HAP; not native execution evidence.
- `tests/language/models/.work/run-2QzMrP`: 70 original model/List/nullable cases,
  flat/modules and original entry parameters on final production sources.
- Diff self-check passed. Independent review remains deferred.
- Cross-feature catch/finally composition and final round gate remain L6 work.
