# UI Migration Tool Architecture

Source-page storage normalization lives in `contracts/source_storage.py`;
writers share repeated values within one file and consumers expand at their
input boundary. Rendering never depends on a sidecar or reopening Android code.
Frontend `content_roles.py`, `root_selection.py` and `route_roots.py` separate
non-visual value expressions, exact entry overload selection and verified
navigation-host facts from component rendering. `SourceTree` derives layout
children from `parent_id`, passing through non-rendering business/slot boundaries
without changing their source ownership. `SourceLayout` measures/places those
outputs under the actual parent and records a union for business-boundary bounds.
Multiple root outputs remain ordered and caller-owned, not an invented Stack.
Unknown parent IDs, cycles and ambiguous entry declarations remain errors.

Value-use positions in PSI (arguments, local initializers and helper returns)
refine inferred expression-bodied composables into value helpers. The annotation
alone does not make a call a UI builder. Known UI emissions and invoked composable
slots take precedence; a mixed value/UI callable is retained with a diagnostic.
Constructing or returning a UI lambda does not execute it. This bounded analysis
is not compiler-level return-type/effect inference. Exact project adapters also
use source declaration lookup for same-file and same-package calls; ambiguous
source overloads are not selected by short name.

## Public Entry Points

### Generated Source Names

Source-backed page structs and business builders preserve the Android symbol and
case (`ProfileScreen`, `ProfileCard`). Private rendering props interfaces use
`renderProfileCardProps`; the source-named business method retains the declaration's
parameter names and mapped types. The frontend writes `source.property_names` naming
hints, PSI-proven `source.property_bindings`/`source.invocation_names` bindings and
`source.component_interface` into the single page JSON. The backend never
reopens Kotlin source. Regenerate older JSON to gain naming information it lacks.

Optional business UI alternative preservation is split across
`frontend/component_ui_states.py` (callee branch collection/context projection),
`contracts/component_ui_states.py` (embedded Lanhu variant validation/decoding), and
`arkui/component_ui_states.py` (one source-named builder with a UI-only selector).
It is opt-in via `--preserve-component-ui-states`; page branch selection stays fixed.

Overloads use parameter-name suffixes, fixed-state specializations use `Variant`,
and genuine name collisions use numeric suffixes. Keywords and invalid target
identifier characters are legalized. Literal-only facts and implementation-only
helpers have no original source symbol; they retain descriptive generated names.
This is UI builder naming, not translation of all application methods or fields.

New output follows the Android source-relative file path (`ui/Card.kt` becomes
`ui/Card.ets` under the selected output directory). Owned legacy entry filenames
are retained on regeneration so existing host imports keep working. Import the
exported type recorded in `manifest.outputs[file].root_component`; do not infer
the exported symbol from the filename.

`arkui/source_modules.py` plans the output set from embedded definition identities.
`arkts_source_modules.cjs` uses the SDK AST to relocate generated builders, interfaces,
calls and imports, preserving string literals and native UI syntax. The shared parser
locator lives in `arkts_sdk.py`; the backend does not import source discovery.
Source-named functions and their private fact helpers are colocated in the source
file. Only functions that transitively require page-owned state/helper access receive
a typed auxiliary context parameter. Infrastructure without source ownership lives in
`_migration/<page-identity>/`. No additional layout node is introduced.

Every file is recorded in the page ownership manifest. Identical modules already
owned by other pages can be reused; differing fixed-state specializations cannot
overwrite shared files. Regeneration checks every old hash before a transactional
write/delete and retains files still referenced by another page. This is source-file
organization for the selected UI, not arbitrary Kotlin or domain-logic translation.

Keep running the existing commands under `scripts/`. Copy/install the complete skill,
not individual Python files; commands now import the adjacent `ui_migration` package.
No new third-party dependency or CLI argument is introduced by this refactoring.

| Entry | Responsibility |
| --- | --- |
| `analyze_compose_project.py` | Safe-source component/call inventory |
| `generate_source_page.py` | Exact Compose root + snapshot/contract + explicit project styles -> source-page.json |
| `migrate_compose_page.py` | Page-level CLI orchestration, stage logs/timing and partial/error results; calls existing tools without new parsing/rendering rules |
| `generate_project_style_definitions.py` | Reusable project-global theme file from the analyzed contract; explicit refresh only |
| `generate_lanhu_source_page.py` | One selected source state to one `version_json.json` |
| `generate_ui_state_previews.py` | Explicit named scenes, each with its own source-state document |
| `generate_arkui_page.py` | One source-generated `version_json.json` to ArkUI and a diagnostic manifest |
| `generate_real_android_page_json.py` / `generate_real_harmony_page_json.py` | Runtime evidence capture/normalization, not target layout input |
| `audit_page_support.py` | Human-readable property support and links to actual implementation owners |

`real_page_pipeline.py` and `layout_expressions.py` preserve existing Python imports
as explicit aliases. They contain no second implementation or alternate translation path.

## Dependency Direction

```text
Safe Android source -> inventory -> fixed-state projection -> Lanhu page document
                                      |
                               PSI expressions

Lanhu page document -> contract validation -> ArkUI layout + drawing -> target files

Source inventory + device tree + screenshots -> runtime mapping / pixel verification
```

Target rendering cannot import the source front end, runtime matching, Kotlin evaluation
or CLI modules. The contract layer cannot import target project operations. Semantics
receives source framework adapters explicitly; it cannot import project orchestration.
The architecture test checks imports, dependency cycles and these direction rules.

## Module Owners

### Registered Controls

New dialog, menu, tab, navigation, flow and grid controls live individually in
`ui_migration/controls/`. A shared registry supplies scanner names, slots, argument
ownership, source-fact projection and target rendering. Each control implements
`project(ProjectionContext)` and `render(RenderContext)`; target rendering only sees
page facts and narrow rendering helpers, never the source evaluator or whole renderer.
See [registered-controls.md](registered-controls.md) for extension steps and limits.

### Source Dependency Analysis

`frontend/source_symbols.py:SourceSymbolIndex` indexes all PSI function declarations,
not only annotated composables. Content inventory and bounded property evaluation
share lexical symbol resolution: declaration file/owner, explicit imports and aliases,
same-package definitions, then wildcard imports. Multiple candidates stay explicit;
argument names/arity can narrow the dependency trace but are not compiler type proof.

`frontend/declaration_lookup.py` narrows function/property candidates by simple and
fully qualified name before applying those same lexical rules. Candidate order and
ambiguity are preserved. Visible properties (including misses) and global values are
cached per declaration file/owner within one `SourceSymbolIndex`; callers receive
their own collection copies. A new index always reads the supplied source again,
so changing branches cannot reuse another index's cached values. No disk cache or
additional CLI argument is introduced.

The contract analyzer's `collect_composable_associations` uses the same declaration
lookup for its `symbol-resolution` loop. It builds the lookup and global name set
once, then applies the unchanged file/import/package rules to matching candidates.
It still queries the full name inventory for every file to preserve the association
contract, but each query no longer linearly scans every project function. Keep this
contract-stage path covered separately from source-page dependency benchmarks.

Snapshot/contract reuse skips project intake, not all source-page analysis. Each
source-page command still parses PSI declarations across the snapshot, including
their syntax bodies. `frontend/dependency_graph.py` materializes dependency edges
only from the requested page root(s) and their transitive closure: calls, parameter
defaults, referenced property initializers and callable references. Ambiguous targets
are all retained, cycles terminate, and a later trace extends the same graph on demand.
Lambda content inspection is limited to reached declarations. Files are not excluded
merely because their path contains `test`, `androidTest` or a sample module.

Whole-project analysis keeps full dependency construction when no roots are supplied.
The page CLI supplies roots automatically; no new argument is needed. This is not
cross-command index reuse or a header-only Kotlin parser. Global declaration scanning
and source-value inventory still have a cost; the optimization removes unrelated deep
dependency analysis without pruning the source-page data inventory.

The index identifies content builders (including lazy scope aliases and scope
parameters), Modifier helpers and value functions, and follows calls from the selected
page entry. Referenced global initializers are traced and evaluated in their declaration
scope. Unrelated function bodies are not evaluated. Conditional dependencies are
conservative in this inventory; the existing fixed-state evaluator selects active
branches and preserves ordered modifiers before target generation.

`source-page.json` adds two diagnostic records:

- `source_dependency_trace`: reached definitions, content/modifier/value roles, call
  edges, explicit ambiguous candidates and external/dynamic calls.
- `source_dependency_gate`: before-page-generation reconciliation of reached source
  content definitions against the UI closure, plus independent PSI call counts for
  catalogued native controls (including import aliases). Missing definitions/controls are named and also
  appended to `unresolved`. Partial output remains permitted; a failed check is not
  silently upgraded to success.

This gate does not prove every leaf/property has been emitted, nor runtime geometry.
External calls are not automatically considered supported. Dynamic dispatch, generated
sources, ambiguous overloads and unsupported expression nodes still need explicit
diagnostics/adapters; this is not Kotlin compiler type analysis. The target still reads
one Lanhu page JSON and never reopens Android source.

Run `python3 -m unittest test_source_dependencies test_source_ui_completeness test_fixed_state_value_parity`
from `scripts/` for scope/alias/parameter/slot/state
regressions, then the existing complete migration suite. New source API adapters must
use the same resolver rather than add a second import/name matching implementation.

All paths below are relative to `scripts/ui_migration/`.

| Responsibility | Owner | Input / Output |
| --- | --- | --- |
| Source symbols, business component inventory | `frontend/definitions.py`, `inventory.py` | Safe text and analyzed calls -> component instances |
| Source framework style adapters | `frontend/styles.py`, `bindings.py`, `theme.py`, `resources.py` | Source arguments and tokens -> declared style facts |
| Persistent global style extraction | `frontend/project_styles.py` | Analyzed theme inventory -> cached definitions embedded in each page; no hash invalidation |
| Selected expression evaluation | `semantics/expressions.py` | PSI tree + bindings + fixed values -> value or explicit unresolved |
| Literal/interpolation and call structure | `semantics/literals.py`, `syntax.py`, `builtins.py` | PSI literal entries, receiver and argument nodes -> bounded pure values |
| Source value adapters | `frontend/values.py`, `source_values.py` | Structured framework calls and inventory-proven factories -> per-field values; no execution of app code |
| Shape values and drawing | `frontend/shapes.py`, `arkui/corners.py` | Typed corner units and physical/relative corners -> native measured-size drawing |
| Modifier/TextStyle projection | `frontend/projection.py` | Evaluated branches + narrow adapters -> selected style facts |
| State visibility, list expansion and display values | `frontend/fixed_state.py`, `preview.py` | Explicit scene -> selected source tree |
| Pager state, pages and native swipe | `frontend/api_adapters/pager.py`, `frontend/pager.py`, `contracts/pager.py`, `arkui/pager.py` | PSI state -> typed page groups -> native Swiper; ordinary page children use existing renderers |
| Ordered modifier wrappers, scaffold padding | `frontend/normalization.py` | Declared modifiers -> preserved native hierarchy |
| Source hierarchy and reference frames | `frontend/source_tree.py`, `reference_layout.py` | Source tree -> reference geometry, never a target bbox fallback |
| Lanhu document serialization | `frontend/lanhu_export.py` | Selected source facts -> version JSON and source phase trace |
| Input validation and identity | `contracts/validation.py`, `lanhu.py`, `identity.py` | Single JSON -> validated nodes and relationships |
| Per-instance consumption checks | `contracts/consumption.py` | Required fields + actual emitted fields -> pass/fail diagnostics |
| Shared required semantics | `contracts/requirements.py` | Component family + real layout parent + fixed state -> required/absent/not-applicable facts |
| Target measure/layout rules | `arkui/layout.py` | Declared sizing/parent constraints -> native layout operations |
| Shared physical-pixel rounding | `arkui/formatting.py` | Logical values -> one shared length helper requirement |
| Native leaf creation | `arkui/leaves.py` | Registered native type -> `LeafResult` (lines, consumed fields, resource status) |
| Surface and typography | `arkui/surface.py`, `typography.py`, `fonts.py` | Explicit facts -> drawing/text operations and field consumption |
| Hierarchy traversal and native containers | `arkui/renderer.py` | Validated tree -> composed layout/drawing output |
| Reusable business UI definitions and call sites | `arkui/business_components.py` | Embedded source identities + projected instances -> named builders, typed data and slots |
| ArkTS component document | `arkui/document.py` | Emitted body + required helpers -> component source |
| Target ownership, assets and filesystem | `arkui/project.py`, `resources.py` | Target-owned resources -> verified outputs |
| Device facts and comparison | `runtime/parsers.py`, `mapping.py`, `pixels.py`, `snapshot.py` | Runtime tree/pixels -> measured facts and unmatched evidence |

## Design Principles In Practice

| Principle | Concrete constraint |
| --- | --- |
| Single responsibility | State selection, validation, measurement, drawing and filesystem writes have different owners. |
| Open/closed | Add native leaves through the handler registry and shared property owners; do not add project-name/page-name branches. |
| Liskov substitution | Leaf handlers all return `LeafResult`; no handler silently substitutes another native type to disguise unsupported behavior. Test the common result contract across the registry. |
| Interface segregation | Layout receives nodes, constraints and recording callbacks; style projection receives only serialization/style adapters. Neither receives the entire orchestrator. |
| Dependency inversion | PSI semantics does not import the source pipeline; adapters are supplied by the source-state composition root. |
| Least knowledge | Surface, typography and document generation do not reach into a renderer's private state; they receive their own explicit inputs. |

Prefer small data objects, protocols and composition. Do not introduce an inheritance
tree, mixins, `__getattr__` forwarding or a service locator simply to reduce line counts.
Pure transformations can remain functions; the goal is a single owner per rule, not a
class for every function.

### One Fixed-Value Path

`frontend.values.value_resolver` composes the PSI evaluator with structured source
adapters. Fixed-state content, dimensions, Modifier arguments and TextStyle projection
use this path. Literal interpolation is emitted as PSI entries (including escapes),
not reconstructed using a `${...}` regular expression. Framework adapters receive
call/receiver/argument nodes and recursively use the same scope. Factories must be
proven by the source inventory; an unknown record field does not invalidate its known
siblings, and cannot be converted into displayed placeholder text.

The old `evaluate_value_leaf` and `evaluate_static_call` public names are aliases,
not independent parsers. The generic `LayoutExpressions` callback parameter remains
for external Python compatibility; production source composition passes the explicit
node adapter. Source inventory and selected framework style serialization still have
bounded lexical adapters; this is not a full Kotlin compiler replacement.

## Adding Or Fixing Support

### Business UI Components

`meta.migration.componentDefinitions` embeds source identities, parameter declarations
and `ui_template.calls` captured before fixed-state projection. Each business layer
retains `migration.definitionId`, `componentKind` and `invocationBindings`. The expanded
layer tree remains the selected UI fact tree for layout and diagnostics. Templates
preserve their original arguments/conditions; target generation does not re-evaluate
Kotlin or reopen source files. These are extensions to the Lanhu-shaped document,
not fields claimed to exist in a native Lanhu export.

The target emitter preserves each supported project component as a source-named
`@Builder` inside the generated page, without an additional layout container.
`frontend/component_interfaces.py` exports the complete source declaration and typed
call arguments; `contracts/component_interfaces.py` defines the type grammar;
`arkui/component_interfaces.py` validates and emits the interface from that one JSON.
Parameter names/order/types come from declarations, including unused business/state
parameters, not inferred text/media values. `render*` helpers and their `Props` are
private fixed-state rendering details, not the public business signature. Parent layout
scope stays on the original native roots, including multiple roots. Selected structure
or non-parameterized style differences yield explicit specializations of the same
source definition, listed in the `.migration/arkui-pages` manifest. A definition count
is not a builder count. Independent source definitions are never deduplicated merely
because they look alike.

Caller-owned composable slots become separate builders and typed `BusinessSlot`
arguments. A generated builder dispatcher implements the selected slot calls without
adding a view: arbitrary function parameters cannot be invoked as ArkUI UI syntax.
Nested slot values retain their own bindings. This is fixed-state UI defunctionalization,
not migration of executable Kotlin callbacks or network/state-management code.

Supported declaration types include primitives, nullable types, nested collections and
function signatures. Unknown domain/annotated types remain explicit diagnostics;
no `any` or string fallback is substituted. See the precise limits in
[business-component-reuse.md](business-component-reuse.md#generated-component-interfaces).
Only observed, distinguishable source states can dispatch different generated bodies;
unrepresentable dispatch retains the private previews with a diagnostic, never an empty
builder. `property_names` is a naming hint; only PSI-proven direct `property_bindings`
can forward a source parameter. A member's terminal name is not a binding proof.

Scope: reusable UI methods within a generated page. This does not yet promise one
shared `.ets` module across independently generated pages, arbitrary domain-type
translation, or automatic ViewModel/event implementation. The manifest
contains definition -> builder -> instance -> render-argument paths for later wiring.
No command-line option or second JSON input is required; regenerate old page JSON to
include the definition records.

1. Locate the failing phase using source facts, the version document, consumed-field
   diagnostics and runtime measurements. Do not modify the generated page by hand.
2. Fix the owner for that family of semantics. A shared `fillMaxWidth`, padding order,
   font or missing-asset problem must not be patched for one project/component name.
3. Add source -> JSON -> target assertions for direct values, referenced parameters,
   selected branches and unknown values. Add the same case to related native types.
4. Update `page_component_catalog.py` and the generated support inventory only when the
   actual supported value domain changes. Code links must resolve to the new owner.
5. Finish a coherent implementation round before the full regression/native gate.
   During edits, syntax/import checks are sufficient unless diagnosing a specific error.
6. Regenerate at least Banking and Ekspensify from their safe snapshots and fixed scenes;
   compile and measure device results. Keep unresolved and whole-page visual scores
   visible. A byte-identical refactor is not evidence that an existing UI defect is fixed.

## Scope And Remaining Work

The old source-emission paths inside `Renderer` are removed; the target does not reopen
Android source or accept a second runtime JSON. The source inventory still contains
bounded lexical/framework adapters, and `frontend/styles.py` and the runtime snapshot
builder remain substantial modules. They are not claimed to be a complete Kotlin
compiler or to support every official API. Move a rule into its semantic owner when
changing it; do not recreate competing parsers in layout or drawing.

Keep screenshots, original app sources, native test copies and timing evidence outside
the skill repository. Numerical Pillow/SSIM checks do not authorize model image inspection.

## Shared Property Rules

`contracts/requirements.py` is the single shared policy registry. Source required
facts, the source gate, the target consumption gate and runtime missing-fact
metrics use it. The target recomputes mandatory requirements from the single JSON;
omitting `required_facts` or labeling a missing mandatory value `resolved` or
`not_applicable` cannot bypass them. `symbolic` required values fail the gate too.
Partial generation remains available; a failed semantic gate never means removing
the control or fabricating a value.

| Context | Required semantics |
| --- | --- |
| Material Card/Surface/Scaffold, app bars, painted buttons, styled input fields | Resolved background for the selected theme/state; transparent paint is explicit zero-alpha ARGB, not null |
| Plain layout/text/image/spacer containers | No implicit background is recorded as not applicable; an explicit unresolved background remains a failure |
| Text and input | Text, font size/weight/color; input line mode, read-only, mask and keyboard facts |
| Image | Resource and content scale; missing asset does not delete its layout/surface |
| Selection/toggle, refresh, slider/divider | Checked/selected or refreshing state, range data or divider color/thickness as applicable |
| Enabled-sensitive controls | Actual boolean enabled state; false is a value, null is unknown |
| Width/height | Explicit constant or existing source sizing/native measurement; never invent a numeric size merely to replace null |
| Child weight/alignment | Actual Row/Column/Box scope, skipping non-rendering project-component wrappers; Card's ColumnScope and text-button RowScope are shared with the emitter; text alignment is not component alignment |

Every gate entry reports the component type, actual parent and fixed state. A
resolved path label alone is not proof that a value survived serialization.
To extend support, add requirements to this registry and generation to the
corresponding framework adapter; do not copy type/parent lists into a second gate.
The registry covers the listed semantics, not all properties/overloads of every
Material version. It does not verify that a non-null color is the correct theme
color or replace runtime geometry/pixel comparison.

The target phase gate includes `layout_decisions`. Each entry identifies the
component, actual layout parent (skipping non-rendering business definitions),
modifier path, axis, constraint source and `applied`, `source_no_op`, or
`unresolved` outcome. Fill and weight record bounded/unbounded incoming axes:
an unbounded scroll-axis no-op is source semantics, not an omitted implementation.
An unsupported parent or intrinsic-fill mapping stays unresolved; a different
successful use of the same modifier path cannot override that failed decision.
The existing required-fact checks retain default expressions and source status.

These records describe emitter decisions, not measured pixels or a universal
layout proof. Other layout rules may have no constraint trace yet. Unknown
facts still allow partial generation with a failing gate; do not delete controls
or invent values to obtain a pass. Use device geometry and screenshot checks for
rendering acceptance.

Source and target phase traces both use `contracts/consumption.py:target_fact_phase`.
Selected modifier projection resets every owned field before applying the selected
operations, including border, rotation and scale; an inactive branch cannot leave
its previous raw-scan drawing facts behind.

`source_string_resources` carries the same selected resource table used by source
style extraction into the fixed-value scope. Resource-backed labels therefore have
one value in visibility conditions and displayed text. Unknown resources remain
unresolved; the target does not reread Android resources or source files.

`migration.style.surface.corner_sizes` is an optional four-corner extension with
`unit` (`dp`, `px`, `percent`) and `value`. It takes precedence over reference
`corner_radius_dp`. Percent corners use the shorter native measured side, including
Compose's vertical-pair scaling, via `onSizeChange`; there is no bbox-to-layout
fallback. The ordinary Lanhu `radius` remains useful reference geometry. See
[AndroidX shape semantics](https://github.com/androidx/androidx/blob/androidx-main/compose/foundation/foundation/src/commonMain/kotlin/androidx/compose/foundation/shape/CornerBasedShape.kt)
and [corner units](https://github.com/androidx/androidx/blob/androidx-main/compose/foundation/foundation/src/commonMain/kotlin/androidx/compose/foundation/shape/CornerSize.kt).
Custom shapes, unsupported overloads and unknown asymmetric layout direction still
produce diagnostics; adding typed units is not a claim of complete Shape support.

### Function-valued UI content

`semantics/callables.py` retains lambda syntax and its lexical value/binding scope.
`frontend/callable_inventory.py` inventories content bodies from PSI separately from
active instances. `frontend/callable_expansion.py` selects a body at the invocation
site during fixed-state projection. Immutable constructor fields, list indexing,
function references and forwarded content parameters use the shared value resolver;
no project-specific class name determines the selected body.

Source page documents carry `source_callable_templates` and
`source_callable_components`. Declaring a lambda does not render it. Each invocation
receives fresh instance IDs, the actual parent layout, argument values and captured
scope. Business calls inside the body retain their definition/instance identity.
Unknown or ambiguous targets and recursive expansion retain a `source.callable`
diagnostic at the callsite; they do not become guessed containers or successful
empty content. The ArkUI backend still consumes a single selected Lanhu JSON and
does not load Android source or evaluate application code.

This bounded mechanism is not Kotlin compiler type resolution or execution of
arbitrary delegates, reflection, network calls or custom layout policies. Content
expansion and support for the controls inside that content are separate gates.
Run `python3 -m unittest test_source_callables test_source_dependencies
test_business_components` and regenerate a real page after changes to these paths.
