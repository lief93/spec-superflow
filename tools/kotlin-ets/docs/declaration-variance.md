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

## Redundant upper bounds

GenericBounds.kt asks official IrTypeSystemContextImpl/isSubtypeOf (which calls
AbstractTypeChecker through createIrTypeCheckerState) whether one declared bound
implies all the others. Only a proven equivalent conjunction becomes one bound.
The pass runs after official/common body lowering and before typed ETS lowering;
source binder identities, names and offsets are unchanged, including copied
helper binders. No target cast, synthetic constraint class or runtime check is
needed for this family. Receiver substitution consumes the same canonical bound.

For example, if SpecificSource extends Producer<Specific>, both orderings of
`where T : Producer<Specific>, T : SpecificSource` emit `T extends SpecificSource`.
Class-owned binders and class-plus-interface bounds use the same proof. Bounds
with different generic instantiations that Kotlin itself rejects never reach
this pass. No bound is selected merely because it is first or is a class.

Independent source-interface constraints use a generated named interface extending
all bounds. The pinned ArkTS SDK rejects intersection syntax
(arkts-no-intersection-types); JS runtime erasure does not justify dropping bounds.
Nonnullable source-class/interface combinations use abstract constraint classes;
use-site projections remain pending.

The late IR pass uses official copyTypeParameters, IrTypeSubstitutor and NameTable.
Free source binders and their bound dependencies are copied and rebound; recursive
bounds refer to the generated constraint with the original type arguments. Source
classes are neither wrapped nor modified to implement a helper. The explicit
ETS_BOUND_CONSTRAINT origin survives as typed target constraint metadata. Only
that generated interface admits a conjunction of its parent contracts; ordinary
source interfaces retain their nominal validation. Runtime objects are unchanged.

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

## Redundant-bound evidence

RED run-5mOBtX passes JVM execution, then reaches the old multiple-bound target
guard. Frozen run-zv3izn passes 50 flat + 50 module outcomes over 61 pinned inputs,
three-file reversed-input determinism and strict host types. The actual IR/target
probe checks both bound orderings and class-owned binders select SpecificSource,
while retaining method, parameter and type-parameter names. The original Cases
and Models module hashes above are unchanged. probe-BuvWYJ retains 40 bounded
receiver outcomes and both independent/nullable-bound exclusions. All frozen
hashes were rechecked before commit.

SDK constructors-sdk-OZE6qi checks all three unchanged generated modules and
compiles ABC/HAP with explicit calls to every public bound fixture. This is not
native runtime or whole-R2 acceptance.

- Variance.ets: 59b241574ab4b7b80f82b626f965d9ffc29e42e5fc60d5debaced1bd6b435855
- Bounds.ets: 8047562c5d53b7a694801fc48c351f63ba8b9686f115bb37c18cff10bed36386

run-TcrMlQ separately records invalid test constraints refused by official Kotlin
itself (inconsistent generic ancestors and two class bounds); it is not counted
as the target regression RED. The successful fixture uses legal source bounds.

## Independent-interface-bound evidence

RED run-YLFDKS passes the JVM oracle, then reaches the original multiple-bound
guard in the unchanged UnsupportedMultipleBounds.kt. Frozen run-1PJVr3 passes
85 flat + 85 module JVM/host outcomes over 64 pinned inputs, strict host types,
five-file reversed-input determinism, actual IR/target ownership and seven
two-parent constraint checks. Cases include independent method/class bounds,
free generic binders, recursive self bounds, chained binders and a diamond.
Official FIR rejects the missing-bound call and all three prior variance errors.
The original three module hashes remain unchanged. probe-rdbzxT retains all
40 bounded-receiver outcomes; the exact old multiple-bound negative is now an
explicit positive, while the nullable-bound and invalid-cycle refusals remain.

Target VAWcMq passes the complete target suite, including eight missing-parent,
nominal-interface and malformed-constraint refusals. SDK constructors-sdk-nHowwC
checks all five unchanged generated modules and compiles ABC/HAP. Its consumer
calls every public fixture. This is not native runtime or whole-R2 acceptance.
Source/test and generated-module hashes were rechecked before publication.

- Variance.ets: 0b24cecee12f1fa1230ef373a3b27829edb565e9b48d740ccee5243f0cc23d3e
- Independent.ets: 1bdd6703333a9334e373cfd936d9f458cae3940f44cdc21593b06eb01bed1577
- UnsupportedMultipleBounds.ets: a5646854deb496dded7778f347513a91b5d952e25384a9097199684c250537a1

## Class and interface conjunctions

ArkTS rejects an interface extending a class. The constraint instead becomes an
abstract class extending the source base and implementing the interface bounds.
The original business class still extends its original base; it is not wrapped,
reparented or instantiated through the constraint. Constructors are unchanged.
Official IrFakeOverrideBuilder with BindToPrivateSymbols merges inherited
contracts; only the abstract signatures are emitted. Calls bind to those
signatures through the official collectRealOverrides relationships. The target
validator retains exact member identities, validates both parents and refuses
invented contracts or dropped accessors. External call handling is unchanged.
The original source inheritance/visibility exclusions still apply.

RED run-iLIvVY executes the JVM oracle before reaching the old multiple-bound
guard. run-j2kaIN exposes a stale interface-field identity after an abstract
getter is introduced. Target jtWrhM exposes missing-accessor acceptance; lBVnWQ
passes after correction, including fourteen constraint refusals and the complete
target suite. The generator does not bypass either identity or property checks.

Frozen run-RPJDce passes 110 flat + 110 module JVM/host results over 65 pinned
inputs. It checks six-file reverse-order determinism, official fake-override
origins/edges and twelve two-parent constraints. Cases cover generic class and
method binders, reversed bounds, return to the original base, private base
storage, property reads/writes and method invocation, including Int limits.
probe-Nqh7ty retains 40 bounded-receiver results and the existing explicit
nullable-bound/cycle refusals. SDK constructors-sdk-8yikIv checks all six
unchanged generated modules and compiles ABC/HAP. No native runtime or whole-R2
acceptance is claimed. Frozen hashes were rechecked before publication.

- Variance.ets: 5fe6690ac0099031bc2059e752ebd8e616c772ef2431ddf8683cf2d75b7d844d
- ClassBounds.ets: 84fa0c6333d13cf15f563a32b7c88304f4d356b623397706bd94852d08fc7131

## Use-site capture contract

The frontend session now lends SourceTypes alongside FunctionBodies. Both type
queries delegate to pinned Kotlin 2.1.20: IrTypeSystemContext.captureFromArguments
with FOR_SUBTYPING, and official isSubtypeOf/AbstractTypeChecker. Retained service
references reject use after the frontend session closes. Official IR objects do
not enter the compiler-independent target program.

Capture preserves an interval, not just a type name. EtsCapturedType records the
read upper bound and write lower bound of a generic argument. An out projection
has no writable value (never); an in projection accepts its lower type and reads
the declared upper bound; a star has no writable value and reads the declared
upper bound. Official capture computes substituted source bounds. When one bound
implies the others, the backend selects it using the official subtype query.
Recursive captures without a representable single upper bound remain unsupported.

The target substitutes these intervals into members and approximates only value
positions: reads use the upper bound, writes the lower bound, and callback inputs
reverse direction. Intervals stay in nested generic arguments for assignment and
bound checks. Capture cannot masquerade as a standalone value type or bypass
member identity, readonly, setter visibility or source-owned generic arity checks.
Module and runtime dependency collection traverse both bounds.

The printer uses the read bound for an ETS generic annotation, e.g. Cell<Value>
for Cell<out Value>. It does not allocate wrappers or change source inheritance,
method names, parameters or expressions. This is a checked translation of legal
Kotlin callers, not a claim that the emitted annotation independently enforces
Kotlin projection restrictions on arbitrary handwritten ETS callers. JS erases
generic annotations; that is not justification to erase our typed-tree contract.

The supported acceptance family here is source-class property reads/writes,
in/out/star, finite nominal bounds and nested projections. Generic-call capture,
recursive and independent capture-bound combinations still require composition
work before R2.3 closure. This does not enable general external collection
projection semantics, reified operations or source referential-equality lowering.
Identity is checked by JVM/host test callers around the same emitted project
function, not by pretending that Kotlin EQEQEQ lowering has been implemented.

## Use-site capture evidence

RED run-aUEER9 reaches the former out-projection rejection after the JVM oracle.
run-T7FxgG separately proves official capture/subtype queries and closed-session
refusals before the target implementation exists. Target bJN2Ih catches accidental
standalone captured values; UnwlgV records the initially overbroad position guard.
Final target aUczhk passes eleven projection refusals plus the existing suite.
run-0NTlUT records unsupported source EQEQEQ; the final harness checks identity
outside the translated source and does not count that operation as implemented.

Frozen run-eL9G8F passes 140 flat + 140 multi-file JVM/host outcomes over 68 pinned
inputs, seven-file reversed-input determinism, strict host types, four retained
target intervals and source method/parameter/file identity checks. It verifies
official in/out/star capture and two closed-session refusals; official FIR rejects
four invalid projection uses, three declaration-variance errors and a missing
bound. Original six module hashes remain unchanged. Bounded-receiver probe-zMFhD7
passes all 40 earlier outcomes and existing explicit nullable/cycle boundaries.

SDK constructors-sdk-cMLKGn checks all seven unchanged generated modules and
compiles ABC/HAP. All recorded input hashes were rechecked. This is not native
runtime, UI parity or whole-R2 acceptance.

- Variance.ets: c6c19da2759b447b22e10a4a25056efc3f62c617814a0e2062818abdb954b347
- Projections.ets: bbfcb471fdd653e046d65f9e8d4f029560eacd563d089b144c28b449c151207d
