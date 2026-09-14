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
| R2.3 in progress | Bounded property overrides, inherited defaults, unique-root/multi-entry native construction and protected constructor visibility accepted; remaining default-helper ownership/capture forms, virtual overloads and generic bounds/variance combinations | Declare each supported family and official-phase prerequisites; preserve names/order/dispatch/storage; positive composition and negative type/identity tests |
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

Next close non-public inherited-method default helper ownership (currently
file-level helpers cannot legally consume protected/private members), then
local/inner constructor capture and initializer-popup combinations. Keep helpers
under the correct source owner using official default/body/type machinery; do
not widen member visibility to make a file-level helper compile. Afterwards
proceed to virtual overloads and remaining generic bounds/variance combinations.

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
