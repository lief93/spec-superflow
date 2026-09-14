# Kotlin to ETS implementation plan

This is the current execution plan. Earlier parallel-batch documents are historical
evidence, not the current backlog. Use the existing non-spec development workflow.

## Acceptance contract

### Current completed increment: bounded images and materialized resources (2026-09-14)

The legacy inventory now drives control priority. Image, Icon and bounded Coil 2
literal-URL AsyncImage each have their own rule file (15 control families total).
Painter resources use the shared CallRule type/value contract, not a private
image expression parser. Static R identity, conditional resource selection and
Painter method parameters reach native Image. Stable size modifiers, explicit
SrcIn tint, alpha, description and bounded ContentScale are supported.
The separate asset tool reuses the existing pure vector converter and copies
bitmaps; it does not consume page JSON. Qualified/ambiguous resources, unsupported
vector metadata and missing media reject. Resources still need installation into
the target module's media directory; no automatic target-project mutation.

Focused resource/real-IR negatives, shared type/slot/state regression, basic
controls, launcher checks and the public materializer -> public compiler ->
unchanged ETS/media SDK build passed. No install/network/visual run. ImageVector,
default inherited tint, complete intrinsic sizing and request-object/loader
semantics remain unsupported. See docs/compose-images.md and its evidence.
Fresh pre-commit verification subsequently passed at the user's request; see
docs/control-migration-verification.md. Independent review and device/visual
acceptance were not performed by that verification turn.

### Current completed increment: per-control rules and basic controls (2026-09-14)

User requested broader Compose coverage and one control family per file.
All twelve control families are now in src/ui/controls; shared CallRule dispatch,
typed values, ordered modifiers and target validation/printing remain common.
Added BasicText, horizontal/vertical dividers, Checkbox and Switch with explicit
parameter limits. Real-IR positives/negatives, emitted Boolean callback execution,
the typed state/slot/Pager regression and one minimal SDK compile passed.
The regenerated original Page.ets is byte-identical to accepted native-06.
No install or visual equivalence claim for new controls; unsupported styles,
nullable selection callbacks and effectful divider thickness reject explicitly.
See docs/compose-basic-controls.md. No new review/commit/push in this increment.

### Current completed increment: unified API dispatch (2026-09-14)

User requested that Compose not maintain an independent adaptation pipeline.
Shared adaptCall now selects Value/Statements/Ui through the same CallRule
contract. Independent scoped control rules and backend library rules share
priority/type-consumption handling. Layout/Text/Button and ArkUI signature
construction were extracted; structural Modifier/state/slot handling is still
framework-specific and not claimed fully decomposed. Focused language and typed
UI tests passed; one regenerated fixture is byte-identical to accepted native-06.
See docs/unified-api-rules.md. No new control coverage or private Onboarding
acceptance is implied; no full integration cycle was run.

### Immediate user priority: Gradle project inputs (2026-09-14)

Before expanding further language/Compose work, expose the new backend through
`--project --module --variant/--compile-task`. Collect actual source files,
transitive classpath and Android SDK inputs using the project's compile task,
not hand-maintained JAR lists. Main owns launcher/core source-list input/docs;
existing dependency worker owns init script and focused real Gradle checks.
Acceptance: launcher failure/no-overwrite tests, real task/transitive input
collection, and one public project-to-ETS run. No page installation or visual
integration is required for this input-boundary increment. Never claim internal
Onboarding support from a collector or simple fixture pass.

Status: this input-boundary increment is complete. Seven launcher checks, real
JVM/Android collector checks (six negatives), public project-to-ETS generation
and host execution, and public Android collect-only passed. Evidence is in
docs/gradle-project-inputs.md. Next private-project run should use this entry to
identify actual backend gaps; general project source pruning/compiler-plugin
equivalence and broader Compose support are not implied by this acceptance.

### Verification cadence (latest user instruction, 2026-09-14)

This overrides earlier per-sub-batch SDK/native requirements below; their past
results remain historical evidence. Small increments run focused semantic,
contract, negative and affected-module tests only. Run minimal actual SDK
compilation when a target syntax/legality change requires it, not a full page.
Full cross-module regression, combined SDK, installation, interaction and visual
comparison are milestone gates: completion of an architectural stage such as R2
or R3, final acceptance, or a substantial cross-module contract/behavior change.
Do not treat each R2A/R2B-style increment as a full-integration milestone.
Track deferred integration separately and never report unrun tests as passed.

- Product: a Kotlin to ETS compiler backend with Compose to native ArkUI adaptation,
  not a screenshot-to-layout generator or a JavaScript intermediary.
- Preserve source method and parameter names, declaration boundaries, argument
  bindings, evaluation order, return values and UI state behavior where ETS permits.
- Renaming or bridges required by reserved words, collisions, overloads, closures
  or ArkUI slots must be minimal, source-linked and reported. Do not manufacture
  render/preview aliases to claim structural fidelity.
- Preserve all supported conditions and state updates. A preview initial value
  cannot replace a program condition. Never silently invent empty content slots,
  default values or stub method bodies for unsupported semantics.
- UI acceptance covers layout, typography, colors, resources, insets, modifier
  order, gestures and state linkage, not just compilation or unresolved counts.
- Same inputs must produce matching observable results in Kotlin and generated
  code. Host execution, actual ETS SDK compilation, ArkVM execution and native
  screenshot/gesture evidence are separate levels and must be labeled as such.
- Full Kotlin/JVM, every Android service and arbitrary binary bytecode translation
  are not presumed supported. Unsupported dependencies must name their ownership,
  source location and required implementation instead of silently degrading.

## Existing baseline

The shared compiler contracts and typed UI representation migration are complete
for the documented subset. Binary inline loading, loops and collections have
bounded implementations, not universal coverage. See docs/typed-ui-integration.md.

Fresh native baseline: /private/tmp/kotlin-ets-native-20260914-01/comparison.html.
Both builds/installs, seven paired states, five touch boundary probes and the
declared numerical image/geometry thresholds passed. The selected bounds differ
by 2px; this is not pixel identity or evidence for arbitrary business pages.

## Ordered integration rounds

Rounds integrate in order. Independent work inside a round runs in parallel with
disjoint write ownership. A lane being done does not make a round accepted.

| Round | Deliverable | Dependency | Status |
| --- | --- | --- | --- |
| R0 | Inventory existing capabilities/evidence and fix acceptance/ownership | Existing backend | Complete for planning; no new capability claimed |
| R1 | Transitive serialized inline dependencies; initial interface/inheritance semantics; bounded collection expansion; UI multi-file ownership | R0/shared contracts | Accepted for the explicitly bounded R1A/R1B cases; remaining limitations retained in later rounds |
| R2 | Generic/member dependency linking; generic dispatch, overloads, nested/local declarations; module visibility and name fidelity | R1 accepted | R2A/R2B/R2C accepted for their finite cases; R2D bounded overload identity/naming implementation underway |
| R3 | Broader language/library semantics: nullability, casts, exceptions/finally, equality, numeric families and collection protocols | R2 accepted | Pending |
| R4 | Compose structure/state completeness: nested slots, reactive derived values, event captures, conditional/repeated UI and list/pager linkage | R3 accepted | Pending |
| R5 | UI fidelity: ordered modifiers, measurement, constraints, text/style inheritance, themes/resources, density/font scale and runtime insets | R4 accepted | Pending |
| R6 | Real-project integration: reproducible dependency inventory, library replacement policy, business component/slot adapters, flat configurable output | R5 accepted | Pending |
| R7 | Fixed multi-page acceptance suite, native semantic checks, capability diagnostics and repeatable release evidence | R6 accepted | Pending |

Each round starts with an explicit finite case list. Split a round into named
sub-batches when necessary; do not mark the whole round complete because one
positive fixture works. The acceptance contract remains the common objective.

## R1 parallel work packages

One integration owner (current task) fixes contract changes, owns common files,
assembles results and accepts evidence. Reuse workers when their scope matches.

| Lane | Bounded first increment | Owns | Required evidence |
| --- | --- | --- | --- |
| Dependency | Entry inline calls another real serialized inline body; resolve reachable declarations using official identities/inliner, not only direct application calls | core/BinaryBodies.kt, core/LibraryInlining.kt, dependency tests/docs | Binary-only consumer vs JVM; missing helper/cycle/provenance negatives; no fabricated body |
| Language | Explicit supported subset of interface, class inheritance and member dispatch, including inherited signatures | language/, focused language tests/docs | Dispatch/override/argument/return parity and source-linked unsupported cases; no name-only dispatch |
| Stdlib | Select a finite missing collection family after checking current coverage; reuse loaded bodies or shared typed runtime | stdlib/, focused stdlib tests/docs | Empty/mutation/order/bounds cases, cross-file values, resolved-call identity rejection |
| Output | UI source-file ownership and imports through the existing EtsProgram/module output, preserving method boundaries | output/, focused output tests/docs; UI changes coordinated | Actual multi-file UI SDK input; name/parameter/collision tests, no printed-source parsing |

Main owns Contract.kt, Tree.kt, Validator.kt, Traversal.kt, Printer.kt, Backend.kt,
CLI wiring and cross-lane integration tests. Workers propose needed shared changes
before depending on them. Never concurrently edit the same file. Main performs
shared contract work locally while workers implement independent established APIs.

## Later-round detail

### R2: declarations and libraries

- Separate source bodies, serialized supported bodies and explicitly replaced APIs.
- Reachable dependency graph, generic substitution, member inline and library
  format/version checks. Prototype KLIB loading separately; do not label ordinary
  JVM signatures as KLIB/IR or promise bytecode decompilation.
- Inheritance/interface dispatch, overload identity, constructors, accessors,
  generic bounds/variance and nested/local declarations have distinct tests.
- Cross-file imports/exports, visibility and collisions must be determined by
  symbols; preserve names unless target syntax makes it impossible.

### R3: general semantics

- Control flow, labeled jumps, early/non-local returns and closures retain ordering
  and capture behavior. Reuse verified official common lowering where possible.
- Null/safe calls/Elvis, casts/type tests, structural/referential equality,
  exceptions and finally need same-input semantic and error-path tests.
- Define supported Int/Long/Float/Double/Char/array/list/set/map/sequence families,
  their runtime representation and mutation/iteration contracts explicitly.
- Standard-library extensions such as map/filter/repeat/let use resolved symbols,
  loaded implementations or typed adapters, never source-string substitutions.

### R4: UI semantics

- Ordinary methods/models and Compose calls use one language lowering and target
  tree. UI adaptation owns controls, attributes, slots and platform effects only.
- Preserve component calls and source methods. Keep inline UI inline where ArkUI
  permits; required builder bridges are documented and kept minimal.
- State initialization/read/write, derived expressions, bindings, slots and
  captured callbacks remain live. Sliding changes page, indicator and button.
- UI coroutine effects need an explicit supported scheduling/cancellation subset.
  Network, storage, analytics and other external effects require target adapters;
  never translate suspend into async while pretending cancellation is equivalent.

### R5: visual semantics

- Modifier order and parent constraints govern layout, clipping, painting, input
  and semantics. No arbitrary wrapper or default layout to hide unsupported rules.
- Fixed source dp maps to target vp under ordinary density. Custom source density,
  measurement and font metrics require explicit tested runtime behavior.
- Text size/weight/line height/tracking/baseline, inherited colors/default styles,
  images and resources, shapes/borders, scrolling and system insets are tested
  individually and in composed cases, including alternative viewport/font scale.
- Compare the same state/locale/theme/environment. Retain original screenshots,
  trees, input hashes and numeric metrics; do not loosen gates to obtain green.

### R6: project integration

- Real dependency/classpath inventory is reproducible and offline-friendly.
- Business reuse is explicit for ambiguous types/slots; content must never become
  an empty callback merely because parameter matching failed.
- Project adapters consume/return typed values or effects through the shared
  contract. Target imports, resources and required helper ownership are validated.
- Separate intermediate artifacts from configurable page/component directories;
  flat output where requested, no hidden generated source tree or overwrite of
  user-owned files. Legacy Python migration remains a separate implementation.

### R7: acceptance and delivery

- Fixed fixtures for language, library and UI interactions plus public multi-page
  examples; no company files leave the internal network.
- Compare source/target declarations, parameter bindings, outputs/errors, native
  interaction and images. Report last-correct/first-wrong artifact and owning layer.
- Publish capability coverage and remaining unsupported cases, not a misleading
  global percentage. A release is not accepted solely from one simple page.
- Keep review/commit/push paused unless the user changes that instruction. User
  absence is not release approval; do not commit unrelated existing modifications.

## Autonomous continuation

- User requests parallel work and automatic next rounds while away. Do not wait
  for a routine "continue" once a bounded increment passes its focused checks.
- At each continuation read this plan and progress.md, reconcile worker status and
  local changes, and finish the current batch before dispatching the next one.
- Reuse existing agents; do not create separate user-facing tasks. Requeue ordinary
  work behind active agents, interrupt only invalidating user corrections.
- Freeze all production writers before combined tests; serialize heavy JVM/SDK
  builds to avoid overload. Parallel design/editing is not parallel SDK saturation.
- Keep commands and evidence tied to actual input/output hashes. Failed attempts
  remain visible; do not mark a lane done from interrupted or stale evidence.
- Each production increment runs focused semantic/contract/affected-module tests.
  Full SDK/native integration follows the milestone cadence above, not every
  increment. Only adb emulator-5560 and hdc 127.0.0.1:15557 are authorized when
  native tests are due. Never use AI image inspection or patch ETS.
- Record progress/evidence per round. Routine engineering choices do not require
  user input. Stop for an unresolved user-owned semantic choice, unavailable
  permission/dependency, unsafe change, explicit user pause or exhausted limits.
- No work outside this plan, no purchase/publication, no company-data upload.
  Stop automated continuation when all rounds are accepted or progress genuinely
  requires the user. Disable the matching heartbeat then; do not idle-poll forever.

## Next action

R1B passed full UI T87aMi, actual SDK apqWX0 (30 unchanged generated files) and
fresh native -03: seven states, five touch boundaries, Hypium, unchanged gates.
Page-owned generated/evaluate-once/slot bridges remain a documented R4 boundary;
source recursion and general Compose are not claimed supported.

R2A finite case list:
- Dependencies: non-reified generic top-level serialized inline bodies, including
  one transitive generic helper. Use official decoding/substitution/inliner. Keep
  reified/member/unsupported format cases explicit until their own later batch.
- Language: invariant source generic class/interface heritage, concrete and
  parameterized parent arguments, non-generic member dispatch and constructor
  forwarding. No variance/default-interface-body/overload/nested-class expansion
  in this increment. Test concrete and generic through-base/interface calls.
- Standard library: existing List map/filter/Iterator chains and Array iterator,
  get/set through generic helper signatures and across files. Array map/filter
  remain unsupported in this increment. Fix only demonstrated type/runtime
  closure gaps, without adding an unrelated collection family or UI resolver.
- Output: typed generic heritage/member imports and source name/parameter fidelity
  through multi-file output plus actual SDK inputs. No aliases to bypass identity.

Main owns generic target heritage substitution/validation and shared contracts;
existing EtsNamedType.arguments/typeParameters are the verified data interface.
R2A accepted: public generic heritage 31 pairs, binary inline 6 pairs, generic
stdlib 32 pairs and existing regression suites passed. Combined SDK BUb5bb
checked 37 unchanged generated files. Native -04 passed fresh generation, both
builds/installs, Hypium, seven states and five boundaries at unchanged tolerances.
This is not completion of all R2 declaration/library capabilities.

R2B finite case list:
- Main shared contract: resolve source-owned members on a type-parameter receiver
  through its declared nonnullable class/interface upper bound. Preserve canonical
  member identity and substituted signature; reject unknown/mismatched members
  and cyclic or unavailable bound resolution rather than bypassing validation.
  Existing EtsTypeParameter.upperBound/EtsMember/EtsNamedType remain the contract.
- Dependency: actual serialized top-level generic extension bodies with nonnullable
  Any bounds, extension receiver evaluation and a transitive generic helper. Add
  original JVM/body-identity/call-site tests first; change loading only for proven
  gaps. No binary member/constructor/reified/unsupported-format expansion.
- Language: source generic parameters bounded by a source-owned class/interface,
  including instantiated generic ancestors and type-parameter bound chains; call
  nongeneric member methods while preserving source names and evaluation order.
  No multiple bounds, variance, generic member methods or overloads in this batch.
- Stdlib: existing List map/filter and Iterator passed through those source-bounded
  generic helpers across files. Check callback/member ordering, source-object
  identity and exact helper closure; no new collection family or expression engine.
- Output: bound-type imports, visibility, names and signatures across files using
  the existing typed target tree; verify correct and malformed members and run
  unchanged modules through the real SDK. No new UI text or alias escape path.
- Integration-discovered language legality: normalize official inlined extension
  receiver temporaries via their IR origin; repair strict-mode eval/arguments
  value bindings with collision-safe symbol naming while retaining legal member
  names and source identity. Keep original failed public-replay evidence. General
  object equality remains R3, not an extra dependency adapter in this batch.

Reuse the four existing workers with the same module ownership and new bounded
fixture directories. Main implements focused bound-receiver target RED/GREEN
before granting heavy compiler slots. Workers may prepare disjoint source/library
fixtures now and must propose any additional contract requirement first. After
freeze run combined semantic/SDK regressions and fresh native -05 before accepting
R2B or dispatching another batch. Review/commit/push remain paused.
Do not dispatch duplicate workers during heartbeat continuations.

R2B accepted: final bounded public language RDPJrE, extension replay k7DNH6,
stdlib qpy2tK, target yAJ7zK and frozen language/UI regressions passed. Combined
SDK RmCrqG checked 44 unchanged generated modules (including older regression
inputs). Fresh native -05 passed both builds/installs, Hypium, seven states and
five touch probes; selected geometry2px, original image thresholds unchanged.
Owned Harmony emulator stopped and its starter process reaped.

R2C contract preparation:
- Main: generic inherited method signatures compare method-owned binders by
  position after class substitution, preserving free identities and exact bounds,
  argument/result types and canonical override/member identities. No variance or
  name-only identity. Tree.kt remains the data contract unless evidence requires
  an explicit extension.
- Language: inventory bounded generic member declarations and interface/base
  overrides before implementing on the fixed contract.
- Dependencies: inventory actual serialized inline default-expression bodies and
  transitive linkage; do not fabricate ordinary binary class implementations.
- Stdlib/output: inventory existing collection families through generic methods,
  cross-file imports, names and target legality. No new UI or collection family.
R2C finite implementation cases after inventory:
- Language: standalone generic method control, generic interface implementation
  with differently named binders, base/fake-override calls across ancestry,
  simultaneous class/method substitution including callbacks, method-bound chains,
  a generic method on a bounded receiver, and receiver/argument/callback order and
  alias identity. Existing exact obsolete negatives become positives only after
  their unchanged source has focused/public proof. No overloads, member extension,
  inherited default args, variance, super calls or nested classes in this batch.
- Dependencies: two actual binary JAR layouts with an Any-bound generic extension
  default value calling a second-JAR helper; omitted/explicit/named arguments,
  primitive/source-object results, identity/mutation and source provenance. Keep
  the conservative requirement to load unused default dependencies explicit;
  call-sensitive dependency policy is deferred, not silently relaxed.
- Stdlib: existing List map/filter/filterNot/Iterator through generic class/member
  helpers, cross-file callback result types, mutation/order/error/identity and
  exact helper closure. No new runtime family without a demonstrated closure gap.
- Output: generic method declarations/calls/bounds and class substitution across
  modules, source names and canonical imports, malformed signatures rejected and
  unchanged target modules tested by actual SDK.
Main target signature RED vNSeVt then GREEN CqlL5v; nongeneric bounded-call extra
type-argument RED r8u7lt is being fixed separately. Existing Tree contract unchanged.
Workers implement disjoint fixtures/owned code in parallel, with no JVM slot until
granted. After freeze run regression/SDK and fresh native -06. Review/commit/push
remain paused.

R2C accepted for the finite cases above: focused/public generic member language,
actual binary default-body replay, generic-method stdlib/module contracts and
frozen language/UI regressions passed. Dedicated SDK MLKL9o checked eight modules;
combined SDK oAEsGZ checked 52 unchanged generated modules, including explicitly
labeled older regression inputs. Fresh native-06 passed generation, both builds,
installs, Hypium 1/1, seven matched states and five touch probes. Original image
thresholds passed; selected geometry delta was 2px. Owned Harmony emulator stopped
and starter session5444 reaped. R2 as a whole remains incomplete.

R2D next bounded contract inventory (read-only before implementation):
- Language: source top-level and non-inherited member overloads; use official
  resolved symbols and inspect Kotlin JS/common naming implementation. Preserve
  unique source names; minimally disambiguate only unavoidable target collisions.
- Dependencies: actual serialized inline overload identities across JAR layouts,
  static selection and provenance; no ordinary JVM body fabrication.
- Stdlib: existing collection families through overload helpers/callbacks,
  evaluation order, identity and exact cross-file runtime closure.
- Output: typed declaration/call/import identities and ETS legality for overloaded
  names. Shared naming contract must be fixed before production edits.
No runtime typeof dispatcher for source numeric overloads that both lower to ETS
number. Inherited virtual overloads, constructor overloads, variance and nested
classes are outside this increment. Reuse the four workers; JVM/SDK slots stay
serialized. Review/commit/push remain paused.

R2D finite implementation grants after inventory:
- Shared target contract: optional sourceName on EtsFunction/function-symbol
  construction preserves original source identity; emitted name remains explicit.
  Duplicate identity guards and exact references are green in target lyjtCh.
- Language: top-level arity and Int/Double/String overloads; calls before
  declarations; nonvirtual final-class methods; generic/concrete static selection
  inside generic forwarders; generic-class/member substitution; recursive sibling
  calls, capture/effect order, suffix/local-name collisions and reversed source
  list input. One declaring IrFile per top-level group; callers may be other
  files. Reuse official NameTable with declaration keys, not target-type strings.
- Dependency: Int/Double actual serialized inline entry/helper overloads with
  distinct markers, omitted/named argument effects, one/two-JAR layouts and
  reversed classpath. Missing selected Double body must not use available Int
  sibling. Duplicate-artifact classpath shadowing is documented, not a new policy.
- Stdlib: existing map/filter/Iterator through those pure overloads and callbacks;
  cross-file order, identity, mutation/error behavior and exact runtime closure.
- Output: sourceName canonical IDs, unique emitted bindings, both overload imports
  from one owner file, member ownership and same-source provenance; negatives for
  genuinely inconsistent IDs/names/types/visibility. Do not call another valid
  same-ETS-signature overload a type error; source IR/JVM traces catch that bug.
Main target compilation complete/reaped. Leibniz exclusively owns the next
focused baseline/current language job chain once its fixtures/source are ready;
all other compiler jobs remain queued. This is not a full frozen SDK/native slot.
Do not start final frozen acceptance while workers edit.
