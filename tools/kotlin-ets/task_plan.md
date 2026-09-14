# Kotlin to ETS implementation plan

This is the sole active execution queue. Follow the overall compiler plan, not
the most recently discovered page/property/API limitation. Historical evidence
and superseded instructions are in docs/execution-history-20260914.md.

## Objective and architecture

Official Kotlin frontend/IR -> semantic lowering -> typed ETS target tree ->
validated ETS/modules/resources. Standard-library/runtime implementations and
platform/framework adapters participate in this chain. Compose is a framework
adapter, not a separate expression parser or snapshot page generator.

Preserve source declarations, method/parameter names, evaluation order, return
values and UI state behavior. Required target naming/slot/runtime bridges must
be minimal and source-linked. Preview inputs never erase program conditions.
Unsupported semantics are diagnosed, not replaced with empty UI or default values.

## Operating rules

- Main assistant implements, tests and self-checks, one requirement at a time.
  No developer/reviewer subagents and no scheduled wakeups.
- Inspect pinned Kotlin common/JS implementations before designing new language
  machinery. Reuse compatible stages; do not transplant JS runtime conventions
  or write API-name string substitutions to approximate language semantics.
- Freeze production and test inputs before acceptance tests. Preserve failed
  evidence. Run focused semantic/target/module tests for each increment; full
  SDK/native/visual integration at round gates or substantial shared-contract changes.
- Commit and push passing, self-checked work without routine reconfirmation.
  Exclude unrelated dirty files. A failed push is not publication.
- Continue to the next queued requirement after acceptance; no ad hoc control
  expansion or repeated page integration in the middle of language work.
- Keep company data inside its permitted environment. Label host, SDK, ArkVM,
  interaction and visual evidence separately; never equate compilation with parity.

## Overall order

| Stage | Deliverable | Current state | Exit gate |
| --- | --- | --- | --- |
| R0 | Architecture, shared interfaces and acceptance contract | Complete for agreed baseline | One typed compiler pipeline and explicit evidence levels |
| R1 | Initial dependency, language, library and module closure | Accepted for documented R1A/B subset | Existing frozen semantic/SDK/native baseline |
| R2 | Declarations, dependency bodies/linking, generic dispatch and module identity | In progress; queue below | Every remaining R2 item has implementation and composition evidence, then combined SDK/native gate |
| R3 | Control flow, nullability/casts, exceptions/finally, equality, numeric and collection semantics | Pending R2 | Same-input normal/error/effect results and runtime/module closure |
| R4 | Compose structure and live UI state, slots/events/repetition/list/pager linkage | Pending R3 | Source boundaries preserved and state/interaction tests pass |
| R5 | Modifier order, constraints/measurement, typography/theme/resources/density/insets | Pending R4 | Matched environment, numerical layout/image checks, no relaxed thresholds |
| R6 | Real offline project dependencies, business adapters/slots and configurable flat output | Pending R5 | Reproducible existing-project build, explicit replacement policy, safe output ownership |
| R7 | Fixed multi-page acceptance and release evidence | Pending R6 | Structure, behavior, interaction and visual acceptance with reproducible commands |

This is bounded Kotlin/Compose support, not a promise to decompile arbitrary JVM
bytecode or translate every Android service. Unsupported format/runtime boundaries
must be explicit. Do not quietly move an unfinished agreed item to a later round.

## Current stage: R2

Accepted evidence already covers generic source heritage/methods, nonvirtual
overloads, cross-file names/visibility, named local/nested declarations, supported
captures/inner chains, bounded serialized inline dependencies and independent
adapter modules. Do not repeat those implementations.

Recent declaration consumers: inherited final properties, interface contracts,
bounded virtual/abstract class properties, and inherited default dispatch with
generic/static-provider composition. See docs/declaration-call-contract.md and
docs/inherited-defaults.md. These do not complete R2.

Execute the following remaining work in order. Each row is an architectural
deliverable, not permission to create an unbounded sequence of tiny API patches.

| Order | Remaining work | Required evidence |
| --- | --- | --- |
| R2.1 accepted | Dependency-body contract and reachable ownership: typed source/serialized origin, precise missing-body reasons, checked target replacements kept separate | policy-trUFhB binary-only consumer and JVM/host parity; r1-V3lFKr transitive identity/negative checks; typed-etvKp3 adapter/source contract |
| R2.2 accepted for selected family | Serialized JVM inline top-level/member/extension generic bodies and call-site binding; separate official KLIB-loader proof | run-OLRVgz/replay-VVr6bu upper-bound/result/rejection closure; KLIB run-MvqSU7 and module run-TP8ttw. Explicit unsupported body/receiver/format boundaries remain |
| R2.3 in progress | Bounded property overrides, default helpers, native construction/protected visibility, capture/heritage composition, source virtual-overload bridges, bounded method/readonly-property covariance, declaration variance, redundant bounds and independent source-class/interface bounds accepted; remaining use-site projection combinations | Declare each supported family and official-phase prerequisites; preserve names/order/dispatch/storage; positive composition and negative type/identity tests |
| R2.4 | Cross-file visibility, declaration ownership, imports/exports and diagnostics for the completed declaration/dependency families | Multi-file output, reversed-input determinism, exact source ownership, no unnecessary aliases, target checks |
| R2 gate | Frozen combined language/library/module regression and SDK/native baseline | Separate evidence for host results, SDK legality and native behavior; whole R2 stays incomplete until accepted |

## Next action

Protected constructor visibility is accepted for the documented source family.
The target contract now uses EtsVisibility for methods, fields and constructors;
source IR visibility drives both factories and official default-stub hooks.
Target tests.9W0mnW includes twelve visibility refusals. Frozen run-VDrnEa passes
90 flat + 90 module JVM/host outcomes, five boundaries, reversed-input determinism
and original constructor symbol/permission checks. SDK constructors-sdk-HfxCh4
checks and compiles six unchanged modules to ABC/HAP. No device/native/UI or
whole-R2 completion follows. See docs/constructors.md for hashes and RED cases.
Inner-chain green-weKarR also retains 20 JVM/flat/module outcomes, source owner
links, strict types, deterministic output and eight precise exclusions.

Default-helper ownership is now accepted for the documented source family:
run-cJb0cl passes 55 flat + 55 module JVM/ETS-host outcomes, five boundaries,
four-file determinism, thirteen source-owned providers and two public widening bridges with
exact argument/type bindings. Class helpers retain source visibility; interface
helpers remain file-level. Target suite tUqicj passes. See inherited-defaults.md;
this increment does not add SDK/native or whole-R2 acceptance.

Unique-root local/inner constructor capture and initializer popup are now accepted:
capture run-EnPet9 passes 40 flat + 40 module outcomes, exact official capture/outer
identities and malformed-prefix rejection. Constructor run-j80b1A retains 90 + 90
outcomes, six former-negative positives and four precise boundaries. Local capture
green-yMMZ1X passes 30 outcomes in each output form and eight malformed IR checks;
inner-chain green-LU6ynq passes 20 outcomes in each form and seven exclusions plus
the former no-primary-root positive. Core run-iuktB1 and target b4JdhD pass.
See constructor-captures.md. These are host/IR checks, not SDK/native acceptance.

Multi-entry stored captures and inner outer links are now accepted for the
documented Any-only family. Capture run-5p3qcZ passes 50 + 50 JVM/host results,
common-prefix/parameter identity, nested outer rebinding and seven malformed
prefix refusals. The common capture arguments occur once, not in each entry slot.
Constructor run-61KOsX passes 90 + 90 outcomes, seven former-negative positives,
four exclusions and unchanged six-module bytes. Inner green-MlqNLI passes 20
outcomes in both forms and fourteen malformed bindings. Target sW4vki passes.
These remain host/IR checks, not SDK/native or whole-R2 acceptance.

Default-provider capture composition is now accepted for the documented family.
Official capture/inner lowering precedes default generation; the official body
movement hook also remaps class receivers inside default closures. Constructor-only
captures may flow through source inheritance without storing another field copy.
Generated names avoid source parameters and descendant members using official
origins, inheritance relationships and JS NameTable. User names remain unchanged.
Defaults run-me1TY3 passes 65 + 65 results, three boundaries, two former-negative
positives, seventeen provider helpers and twenty-nine exact helper calls. Capture
run-su7vhA and constructor run-TjgMb4 pass 50 + 50 and 90 + 90 with unchanged
flat/module hashes. Local core run-NhO261, source-inline run-l3QFlx and target
zWviDp pass. See inherited-defaults.md. No SDK/native or whole-R2 acceptance follows.

Bounded stored-capture heritage initialization is now accepted. Official source
prefixes remain unchanged; the typed ETS consumer places exact captured writes
after each super only after source ancestor checks prove the supported
non-observing boundary. Own stored/default reads are distinct from virtual/custom
getter execution and escaping this. Source names and visibility remain unchanged;
only generated storage uses collision-safe names. Capture run-B1ru9k passes
60 + 60 results, four source boundaries and seven malformed-prefix refusals.
Constructor run-7GLvPv retains 90 + 90, eight former-negative positives and three
boundaries. Local run-aoxicY, defaults run-7u6frm (65 + 65) and target K3HkGP pass.
All frozen source/test hashes remain unchanged. See constructor-captures.md.
This does not support observing pre-super initialization, anonymous owners or
generic/non-Any inner owners, and does not claim SDK/native or whole-R2 acceptance.

Non-bridging virtual overloads now reuse official allOverridden and JS NameTable
to share emitted names along resolved override edges, including generic source
inheritance and inherited defaults. Frozen run-jawUJj passes 30 + 30 JVM/host
results, 18 override edges, 24 typed calls and five explicit boundaries.
Legacy probe-MYKake and public-WOX202 pass, including 45 public-entry results.
Target qOWcdI preserves exact override/call identity validation even when both
source overloads erase to the same target type. See virtual-overloads.md.
Inherited-default run-Clbp2s also passes 65 + 65 results, three boundaries and
29 exact helper calls on this compiler version.

Source joined-slot bridges now directly reuse common generateBridges,
IrBasedFunctionHandle and findConcreteSuperDeclaration. Typed ETS forwarding
preserves the original body and virtual dispatch; abstract contracts receive
only required declarations. Frozen bridge run-SXU2DE passes 45 + 45 results,
14 official edges (four inherited), four target refusals and a separate R3
bottom-string boundary. Overload run-7fboeZ retains 30 + 30, 18 override edges,
24 calls and unchanged output hashes. Target CzNQES passes the strengthened
abstract-entry contract. See virtual-overloads.md for scope and hashes.
Inherited-default run-OHKB8f retains 65 + 65 results, three boundaries and 29
helper calls. Final frozen inputs are unchanged; no SDK/native acceptance follows.

Bounded method-result covariance now relies on official FIR override checking
and the existing official IR substitutions/bridge planner. The target checker
keeps parameters and method bounds invariant, and checks result assignability.
Frozen run-j3vMHT passes 65 + 65 JVM/host outcomes, 19 actual bridge edges (six
inherited), original names/return types, five-file determinism and malformed-target
refusals. Official FIR rejects three invalid override forms before output. Target
RFklC1 and overload run-CxQNDW (30 + 30, unchanged original output hashes) pass.
See virtual-overloads.md; no SDK/native or whole-R2 claim.

Readonly-property covariance is now accepted with writable contracts invariant.
Official FIR decides Kotlin override legality; the target checks mapped result
assignability and exact declared field/getter identities, including cross-file
reads through generic bounds. Frozen run-n2dIZP passes 70 + 70 JVM/host outcomes,
six-file determinism, 19 bridge edges, two property-identity refusals and four
official invalid-override refusals. Legacy run-iSM7AH and target GAopcC pass;
all frozen inputs were rechecked. See virtual-overloads.md. No SDK/native claim.

Source declaration-site IN/OUT is now accepted for the documented family.
Official FIR validates source positions; the typed ETS tree preserves variance,
and the target validates mapped usage and nominal argument assignability without
runtime wrappers or casts. run-EGmIHJ passes 30 + 30 outcomes, strict host types,
two-file determinism, official IR metadata/identity checks and three FIR refusals.
Target CvNTnK and regressions run-Q0nOFp, probe-wKg0i8 and cli-tsbVXo pass.
SDK constructors-sdk-YlGtpt checks both unchanged modules and produces ABC/HAP.
See declaration-variance.md. This is SDK legality, not native or whole-R2 parity.

Redundant multiple bounds now use official IR isSubtypeOf/AbstractTypeChecker:
only a declared bound proven to imply all others replaces the conjunction.
run-zv3izn passes 50 + 50 results, three-file determinism, canonical bound/name
checks and unchanged original two-module bytes. probe-BuvWYJ retains 40 results
and independent/nullable-bound refusals. SDK constructors-sdk-OZE6qi checks all
three unchanged modules and compiles ABC/HAP. See declaration-variance.md.

Independent source-interface bounds now preserve the conjunction with a named IR
interface using official binder copying, substitution and naming. Frozen
run-1PJVr3 passes 85 + 85 results, five-file determinism, seven actual IR/target
constraint checks and missing-bound FIR refusal. probe-rdbzxT retains 40 results;
target VAWcMq passes eight new negative contracts and the full target suite.
SDK constructors-sdk-nHowwC checks all five unchanged modules and compiles ABC/HAP.
See declaration-variance.md. No wrapper, discarded bound or native parity claim.

Source-class/interface conjunctions now use abstract constraint classes with
official IrFakeOverrideBuilder member merging and override-linked call binding.
Frozen run-RPJDce passes 110 + 110 results across six deterministic files and
actual fake-override checks; target lBVnWQ passes fourteen constraint refusals.
probe-Nqh7ty retains 40 results. SDK constructors-sdk-8yikIv checks the six
unchanged modules and compiles ABC/HAP. No business-class reparenting or wrapper.
See declaration-variance.md. R2.4 must also check generated-constraint member
provenance against original declarations and the owning bound locations.

Next implement use-site projection combinations,
inspecting the pinned common/JS type substitution and override
contracts first. External inherited slots, private shadowing and the documented
unsupported receiver/parameter families remain explicit, not silently enabled.
R2.3 is not complete. R2.4 and the combined SDK/native R2 gate remain queued
before R3-R7; these host checks do not satisfy that gate.

Earlier native-constructor milestone:

Public source multi-entry constructor dispatch is accepted for the documented
family. It reuses common default stubs/injection, initializer
lowering/cleanup, body movement, generic remapping and inlining. The typed target
validator now also understands single-execution do/false returnable blocks;
potentially repeating super loops and uninitialized exits remain rejected.
Target suite MM97q9 passes. Final frozen source run-1kz5Yn passes 85 flat + 85
module results, six boundaries, deterministic modules and constructor identity
checks. It includes final-class native entry privacy, generic derived allocation,
inline constructor references and inherited-body initialization safety.
SDK constructors-sdk-jxO1FE checks and compiles the five unchanged public-CLI
modules to ABC/HAP. This is not native runtime or whole-R2 acceptance.
See docs/native-constructor-flow.md and docs/constructors.md. Never use JS
newTarget/prototype allocation or bypass target validation.

Use the inspected official constructor, delegation and initializer contracts.
Do not replace constructor semantics with a renamed function: preserve delegation,
allocation, field/init order, argument effects and source ownership.

Unique-root no-primary GREEN run-pRFuAP passes 60 flat + 60 multi-file JVM/host
results, strict target types, six JVM-valid boundaries, deterministic modules,
seventeen symbol-bound factories and seven original secondary native roots.
It also checks direct native super across classes, including an abstract base.
No source constructor is falsely relabeled primary. RED run-HarJRs records the
previous no-primary guard. This was the unique-root milestone; the current
multi-entry work and remaining capture/visibility combinations are tracked above.
Final inherited-default regression run-QYxcPz passes 45 flat + 45 module
outcomes, five boundaries and common provider/dispatch checks on this version.

Constructor GREEN run-am3R7S passes 40 flat + 40 multi-file JVM/host results,
strict target types, six JVM-valid boundaries, deterministic modules and eleven
symbol-bound factories. RED run-a0L4bN exposed inlined constructor references
bypassing secondary behavior; the fix follows official ordering by converting
constructors after inlining. Final inline run-SrqVTj and local run-JnyUAl pass.
The native-primary this-chain family is accepted, not the remaining allocation
families or all constructor semantics. See docs/constructors.md. No SDK/native
or whole-R2 acceptance is claimed.

Inherited-default GREEN run-SX8Kmd passes 45 flat + 45 multi-file JVM/host results,
strict target types, five boundaries, deterministic modules and actual common IR
provider/origin/call links. Inheritance run-01X601 (50 results/nine boundaries),
inline run-oEZoyZ and concatenation run-wjEgjD pass. The bounded property family
remains accepted; all default/property exclusions are explicit in the declaration
contracts. In particular local/inner default providers still need capture/phase
composition; super, variance and other unsupported forms are not silently enabled.
No SDK/native or whole-R2 acceptance is claimed by these focused checks.

R2.2's selected binary-inline family and its required separate KLIB proof are
accepted with the documented exclusions. Public KLIB input/session/phase support
is not implemented or claimed by the proof; ordinary JVM bytecode is not IR.
See docs/r2e-binary-members.md and docs/klib-loader-proof.md. Do not reimplement
generic substitution or return to already accepted bounded dependency work.

R2.1 and R2.2 are accepted for their documented bounded contracts, not a
general dependency linker. Proceed to R2.3, R2.4 and the R2 gate. R3-R7
retain the deliverables above; each receives its finite implementation/test queue
when its prerequisites are accepted. No claim that pending stages are implemented.

## Latest evidence and publication

- 72e3379: inherited properties; 66 JVM/host results across inheritance suites;
  target type/name checks. Push succeeded, including preceding 44fb21a.
- 153c5c4: interface properties; 40 JVM/host results, 11 source-linked boundaries,
  complete target suite including eight new negative cases. No SDK/native claim.
  Published by the subsequent successful push through 2d038ee.
- Per-increment evidence lives in the corresponding docs and test .work results.
  Do not use historical Next action/worker instructions as the active queue.
