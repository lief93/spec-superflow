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

Recent declaration consumers: inherited final properties and abstract interface
property contracts with final field/accessor implementations. See
docs/declaration-call-contract.md. These do not complete R2.

Execute the following remaining work in order. Each row is an architectural
deliverable, not permission to create an unbounded sequence of tiny API patches.

| Order | Remaining work | Required evidence |
| --- | --- | --- |
| R2.1 accepted | Dependency-body contract and reachable ownership: typed source/serialized origin, precise missing-body reasons, checked target replacements kept separate | policy-trUFhB binary-only consumer and JVM/host parity; r1-V3lFKr transitive identity/negative checks; typed-etvKp3 adapter/source contract |
| R2.2 | Complete the selected dependency linking family under that contract, including generic/member substitutions and call-site binding; investigate KLIB through a separate official-loader proof, not the JVM signature reader | JVM/ETS same-input results, real loaded body provenance, cross-file/runtime closure, unsupported formats explicitly rejected |
| R2.3 | Remaining declaration/call semantics: class property overrides, inherited default arguments, constructor forms, virtual overloads and remaining generic bounds/variance combinations | Declare each supported family and official-phase prerequisites; preserve names/order/dispatch/storage; positive composition and negative type/identity tests |
| R2.4 | Cross-file visibility, declaration ownership, imports/exports and diagnostics for the completed declaration/dependency families | Multi-file output, reversed-input determinism, exact source ownership, no unnecessary aliases, target checks |
| R2 gate | Frozen combined language/library/module regression and SDK/native baseline | Separate evidence for host results, SDK legality and native behavior; whole R2 stays incomplete until accepted |

## Next action

Continue R2.2. The bounded method-generic member route now reuses the existing
official registration/deserializer/inliner and passes frozen IR plus strict host
type/result checks; see docs/r2e-binary-members.md. Binary provenance is excluded
from source-owned declaration emission. Do not reimplement generic substitution.
The separate official KLIB proof now loads real bodies and links three modules
through the same ETS backend; see docs/klib-loader-proof.md. Public KLIB input,
session/body-origin and phase-context integration are not implemented by that
proof. The JVM signature reader is not a KLIB frontend.
Stateless member extension-receiver binding now also reuses that existing
deserializer/inliner: run-KLzVJm plus replay-SCNjcq validate both receiver
identities, generic defaults and result/effect order. Only its blanket guard was
removed; see docs/r2e-binary-members.md.
Next close the bounded generic upper-bound/call-site combinations under the
same dependency-body contract. KLIB production session/phase integration remains
separate from its accepted proof. Keep receiver/state/format exclusions explicit;
do not start page-specific features or jump to class property overrides.

R2.1 is accepted for the documented bounded body/replacement contract, not a
general dependency linker. Proceed to R2.2, then R2.3, R2.4 and the R2 gate. R3-R7
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
