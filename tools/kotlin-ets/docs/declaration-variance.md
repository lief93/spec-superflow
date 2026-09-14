# Declaration-site variance

## Official reuse

Pinned Kotlin 2.1.20's already-executed FirClassVarianceChecker checks source
variance positions, including inherited types, callable inputs/outputs, writable
properties, nested type arguments and visibility. FirTypeParameterVarianceChecker
restricts declaration-site variance to class parameters. IrTypeSubstitutor and
getAllSubstitutedSupertypes remain responsible for resolved Kotlin receiver and
ancestor substitution. No second Kotlin parser or subtype solver is added.

The JS backend's JsClassGenerator emits runtime classes without generic type
annotations. Its runtime erasure is not the ETS implementation: ETS retains
generic declarations and must validate the target-visible contracts. The target
tree therefore carries EtsVariance on class-owned binders. Function/factory
binders remain invariant; copying a class binder into a helper does not make
variance a legal function declaration annotation.

## ETS responsibility

For the same source-owned nominal constructor, target assignability compares
arguments in their declared direction: OUT forward, IN reverse, INVARIANT exact.
Existing nominal ancestry, upper-bound substitution and nullable checks compose
with this comparison. Unknown/external generic declarations do not acquire
variance by their name. Names, symbol ownership and argument arity stay checked.

The target validator independently checks the mapped public/protected declaration
surface, preventing an adapter or target rewrite from putting an OUT binder in
an input or writable slot. Callback inputs reverse position; invariant containers
require invariant usage. Constructors and private storage do not expose mutable
instance operations; static functions have separate binders. This is a target
contract check, not reimplementation of source inference or FIR resolution.

The printer emits ordinary ETS generic syntax, e.g. Producer<T>, read(): T and
Consumer<T>.accept(value: T). There is no per-conversion cast, wrapper, duplicated
method, name suffix, runtime type test or new runtime library. SDK acceptance of
this target form is tracked separately from JVM/host behavior.

## Boundary

This increment covers source declaration-site IN/OUT, composed nominal ancestry,
readonly properties, nested arguments, nullable results and supported single
generic bounds. Use-site projections, star projections, reified declarations,
multiple independent upper bounds and generic external dependency variance are
not implicitly enabled. Kotlin UnsafeVariance does not bypass target validation.
See task_plan.md for the remaining R2 queue; this increment is not all of R2.

## Evidence

RED run-rKbhpm passes the original JVM oracle and then reaches the old variant
declaration rejection. Target 3kObJ7 independently fails safe Producer<Dog> to
Producer<Animal> assignment. Focused run-Fo4KK6 passes 30 flat + 30 module JVM/host
outcomes and reversed two-file output before strengthening declaration-identity
and official IR metadata checks.

Frozen run-EGmIHJ passes 30 flat + 30 module outcomes over 59 pinned inputs,
two-file reversed-input determinism, strict host types and three official FIR
variance refusals. The real IR probe compares declaration names, parameter names,
variance and file ownership, and rejects erased producer metadata. Target CvNTnK
passes nine position/conversion refusals and the existing target suite.

Regression run-Q0nOFp retains 31 generic heritage results and one remaining
boundary; probe-wKg0i8 retains 40 bounded-receiver results and two remaining
boundaries. cli-tsbVXo retains twelve generic results and two boundaries. All
three unchanged former variance-negative fixtures have explicit positive output
checks. Source/test hashes in the frozen runners were verified again.

SDK constructors-sdk-YlGtpt reuses the existing SDK module verifier with an
explicit consumer. Both unchanged modules appear in checker/build records and
compile to ABC/HAP. This proves target legality, not native runtime or UI parity.

- Variance.ets: da878360cac06abec512f82de08829789a2e0a9a4a4838ae03fa5636db7743e2
- Cases.ets: 682ecdf609d79b970a22ef2d6b8df1f3bf3c31782451e18995a360540c006eaf
- Models.ets: 6cf599924a8a9895dd2382f317aed615b0d276ad0371fc9ca5c5c957b0b50938
- SDK modules.abc: e8096b4ba10742c702d8998585969d38bd3df7ed36b12cdcfe1943b4f85f9c0a

Reproduce from repository root:

```sh
node tools/kotlin-ets/tests/inheritance/variance/run.mjs
bash tools/kotlin-ets/tests/target/run.sh
node tools/kotlin-ets/tests/constructors/sdk.mjs <successful-variance-evidence> tools/kotlin-ets/tests/inheritance/variance/Index.ets
```
