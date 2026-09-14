# Native constructor control flow

This describes the ETS constructor-flow contract and its source-dispatch
integration. Both use the official Kotlin IR and the common typed ETS tree, not
an alternate source parser.

## Target contract

The old target validator required exactly one `super` statement in the first
position. ArkTS also accepts argument preparation and mutually exclusive native
`super` branches. The validator now tracks uninitialized/initialized normal paths
through typed blocks and conditional branches:

- Every normally finishing or returning derived-constructor path initializes
  its direct base exactly once.
- A throwing path need not initialize an object it never returns.
- Any `this` read, write or closure capture before initialization is rejected,
  including parameter defaults, conditions and super arguments.
- Nested function/lambda and potentially repeating loop super calls remain
  explicit rejections. A `do/false` loop executes at most once; its normal,
  labeled break and continue exits preserve initialization state, including
  exits from inner loops. This accepts common inliner returnable blocks without
  accepting loops that can allocate twice or skip initialization.
- Only identity-authorized super nodes in the owning constructor reach the
  existing type, argument and base-class checks. Ordinary methods cannot use
  those permissions. Readonly-field and closure checks remain in force.

This deliberately validates target allocation safety rather than re-running
Kotlin symbol, type or constructor-delegation analysis. Existing typed nodes,
traversal and printer are reused; no constructor text is injected into ETS.

## Official phase integration

Kotlin 2.1.20 common `DefaultArgumentStubGenerator` already supports constructors:
it selects masked default arguments and delegates to the original constructor.
`DefaultParameterInjector` rewrites both allocation and delegating constructor
calls. ConstructorDispatch reuses those contracts for selected source families,
without JVM constructor-marker parameters or a separate default evaluator.

The common `FunctionInlining` phase can remap parameters, generic types and
returns in compiler-owned initializer helpers. Its function-access visitor does
not inline `IrDelegatingConstructorCall` directly, so constructor allocation and
initializer helpers must have explicit identities. The official JS
synthetic-primary/ES6 phases provide the structural reference but depend on
JS newTarget/prototype/box intrinsics. Those intrinsics are not native ETS
allocation operations.

The source pass selects multiple-root families, abstract families and source
base classes addressed through a secondary constructor. Common initializer
lowering and cleanup run before helper-body movement, so parameter/property and
init statements are rebound by the official inliner with the constructor body.
Initializer helpers disappear after inlining. A tagged native constructor and
typed nullable argument slots preserve one allocation on the actual derived
object; source-visible constructor calls use symbol-bound static factories.
Generic class parameters remain class-owned in initializer helpers and are
remapped to factory type parameters by official utilities.
Final classes keep the tagged native entry private; source constructor factories
retain original visibility. Extensible families require an accessible native
entry for real derived-object initialization, not a base-object factory.

The language consumer handles nested delegation through its existing statement
and argument lowering. The target validator, not a special printer, authorizes
each super node. No fake primary flag or raw target constructor text is used.
Inherited-initializer `this` safety checks run before official initializer
expansion, so cleanup cannot erase an existing unsupported-semantics boundary.
The same guard covers selected inherited constructor bodies: writes to this
class's own fields/default final setters are allowed, but reads, captures and
virtual calls on the partially initialized instance remain diagnosed. Base
secondary bodies execute before derived fields, just like base init blocks.
Local initializer classes are diagnosed until the official popup prerequisite
can be composed safely. This constructor family does not close R2.3.

## Verification

Run `bash tools/kotlin-ets/tests/target/run.sh`. It prints an evidence directory.
Then pass that directory's `test.jar` to:

```sh
node tools/kotlin-ets/tests/constructors/flow/verify.mjs /absolute/evidence/test.jar
```

The jar must be from the just-completed target suite with unchanged source/test
inputs. The SDK harness records its hash and the corresponding target/test
hashes. It runs the typed fixture through EtsValidator and EtsPrinter, compares
six results with the Kotlin/JVM oracle, checks strict host types, copies output
unchanged into the SDK host and verifies the compiler input, ABC and HAP.

Recorded evidence:

- RED target-tests.x5XKir fails the old first-super guard on a valid branch tree.
- GREEN target-tests.Zzky1G passes the full target suite, including sixteen
  source-linked constructor-flow rejection cases and positive branch/block/exit
  cases. The prior late-super negative is now a positive argument-preparation
  regression, not removed coverage.
- SDK constructor-flow-Mbg3Mw passes six JVM/ETS-host outcomes and compiles the
  unchanged typed-target ETS to ABC/HAP. This is not a public Kotlin-to-ETS
  conversion test and not device/runtime or visual acceptance.
- A preliminary handwritten SDK probe also confirmed the platform rule;
  constructor-branch-f1TZYx failed because its host lacked EntryAbility, not due
  to constructor syntax. Corrected constructor-branch-fvr1RW compiled. Final
  acceptance above uses printer output, not the handwritten probe.
- Final public-CLI regression run-tNKu0Y passes 60 flat + 60 multi-file JVM/host
  constructor results, six source-linked boundaries and real constructor/factory
  identity assertions. Its generated bytes match the preceding accepted version.
- Follow-up self-check RED target-tests.7mnPpR exposed a pre-super loop containing
  a constructor return that the nested-node scan missed. Loop bodies now also
  pass through exit validation without assuming the loop executes. GREEN
  target-tests.V2MFnd passes the complete suite with seventeen rejection cases.
  The earlier SDK evidence predates this guard-only correction; it is not a
  new SDK claim for changed generated code.
- Multi-entry target RED target-tests.XHNdij rejected the common inliner's
  single-execution returnable block. GREEN target-tests.MM97q9 passes the full
  target suite with twenty-two source-linked constructor-flow refusals,
  including early/outer break, continue and duplicate initialization.
- Public source run-BaC9cY first passed 85 flat + 85 module outcomes. Self-check
  then exposed bypassed inherited-initializer `this` guards; the CLI accepted
  DispatchInheritedInitialization before the shared guard was restored.
  Runs run-xfOroR and run-VWFBmj pass five rejection boundaries, 85 flat + 85
  module results, reversed-input determinism and real IR identity checks.
  The latter also covers generic derived construction and an inline constructor
  reference. Native entry privacy changed afterward; these are intermediate
  evidence, not final-version SDK acceptance.
- Final frozen run-1kz5Yn passes 85 flat + 85 multi-file JVM/ETS-host outcomes,
  strict host types, three former rejection inputs as positive regressions,
  six source-linked boundaries and all IR identity/binding checks. All 73
  frozen implementation/test inputs match. The final guard also covers virtual
  calls in secondary bodies (DispatchVirtualBody), not just property/init blocks.
  Flat ETS SHA-256: `7e9c83371ae8847ff8db7840e34ad2301f2b4ac15905338c9be45eb5863a9458`.
- SDK constructors-sdk-jxO1FE consumes that result, verifies source/output hashes,
  clean semantic checker records and runtime module coverage, and compiles all
  five unchanged ETS modules to ABC/HAP. Dispatch.ets SHA-256:
  `8ba813eb1a020a0d125c8418a911cc2f464d7bcb2e1d988aa167e0b5a677c471`.
  This is actual public-source conversion plus SDK compilation, not device
  execution or UI parity. Main self-check and whitespace validation pass;
  R2's combined native gate and remaining declaration families stay pending.
