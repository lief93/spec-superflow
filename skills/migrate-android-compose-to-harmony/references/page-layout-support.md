# Single-JSON Layout Support

The public renderer accepts one `--page-json version_json.json`. Android source is
read only by the earlier source inventory step. Target-owned image/font files
remain resource dependencies, not a second layout input. Do not count branches in
the legacy source-definition translator as support for this entry point.

For executable setup and file provenance, read [Source to Lanhu JSON to ArkUI](source-page-workflow.md).

## Current Mapping

See [the per-control/property inventory](page-support-inventory.md) and its CSV
for the finite active type list, applicable field counts, source/consumer code
references, and unsupported boundaries. Rebuild it with `audit_page_support.py`.
An accepted type name is not a claim that all Material defaults and slots work.

Paths below are relative to `scripts/`. These are implemented mappings, not a
claim that every Compose modifier combination is equivalent.

| Input | Source facts | Active target consumer | Boundary |
| --- | --- | --- | --- |
| Row/Column | source hierarchy, child order | `page_snapshot_component_lines` | native Row/Column; no screen-position fallback |
| Box/BoxWithConstraints | contentAlignment, children | `page_snapshot_container_alignment_lines` | Stack with nine-way content alignment |
| Surface / AnimatedVisibility | explicit surface color/contentColor/shape; selected visible state | native Stack with retained children | settled UI only; unknown theme/content colors remain unresolved, no transition animation parity claim |
| PullToRefreshBox | isRefreshing, contentAlignment, modifier and content children | `static_style_for_call`, `page_snapshot_component_lines` | Box/Stack with an overlaid native loading indicator; fixed-state UI only, preserves weight and child alignment; spinner animation is approximate, not pixel-identical Material chrome; custom indicator/state remain unresolved without deleting content |
| Project component | expanded internal tree and slot ownership | `page_snapshot_component_lines` | retain the expanded children; unsupported composition remains unresolved, not a blanket one-child rule |
| ConstraintLayout | normalized link/center relationships | `page_snapshot_constraint_alignment_lines` | only declared supported anchors; no guessed positions |
| size(width,height), size(DpSize) | `size_arguments`, `static_style_for_call`, component parameter binding | `page_snapshot_dimension_lines` | positional/named constant dp values; official DpSize constructors, local aliases, width/height members, defaults and caller overrides through project components (including forwarded Modifier.size); unresolved calls/Unspecified remain flagged |
| image intrinsic size | `style.asset.width_dp/height_dp`, separate from modifier sizes in `style.layout` | `page_snapshot_intrinsic_image_lines` | Fit/Inside uses native bounded measurement and aspect ratio; explicit sizes/fill still take precedence; unverified intrinsic scaling modes fail |
| fillMaxWidth/Height/Size | `normalized_layout_rules` | `page_snapshot_dimension_lines` | constant fractions; unknown fraction remains unresolved |
| wrapContent/intrinsic | `normalized_layout_rules` | `page_snapshot_dimension_lines`, `page_snapshot_stretched_axis` | native content measurement and full cross-axis stretch, including single-root project wrappers; unsupported intrinsic fill axes/fractions fail |
| weight | ratio and fill in layoutRules | `page_snapshot_source_layout_weight` | native layoutWeight for fill=true; fill=false fails explicitly |
| widthIn/heightIn/sizeIn | min/max constraints in layoutRules | constraintSize branch | constant nonnegative bounds; min must not exceed max |
| child align | Alignment enum in layoutRules | alignSelf/layoutGravity branch | Row/Column cross-axis; Stack uses nine-way LocalizedAlignment layoutGravity (API 20), not the child's internal content alignment; invalid scope remains unresolved |
| fixed-state layout expressions | Kotlin PSI + instance parameter/local scopes | selected modifier chain and layout arguments | nested if/when, aliases, then, scalar arithmetic, DpSize members; unknown branches do not apply either branch |
| explicit offset | normalized offset layoutRules | `page_snapshot_explicit_offset_line` | constants use declared dp; parent fractions use the bounded BoxWithConstraints scope's target onSizeChange, not reference rectangles; wrap/unbounded scope fails |
| arrangement | alignment and spacedBy | `page_snapshot_arrangement_space`, `page_snapshot_container_alignment_lines` | includes spacing plus main-axis alignment |
| padding/margin | edge values and ordered layout wrappers | padding/margin branches | supported prefix outer padding wraps native/explicit surfaces separately from contentPadding; repeated outer padding retained; general interleaved drawing/duplicate axis sizes remain unsupported |
| aspect ratio/direction | resolved style fields | aspectRatio/direction branches | constant ratio and ltr/rtl |
| scroll/LazyRow/LazyColumn | scroll rule and complete child tree | Scroll wrapping native Row/Column | eager expanded children; does not claim lazy virtualization; reverse scroll unsupported |
| top app bar | Material3 64dp content plus outer padding | measured container and centered title | small centered bar, not collapsing/large bar variants |
| font family | `page_font_faces` serializes family/resource/weight | `load_page_font_faces`, font registration | target font SHA checked; unknown family is not counted as consumed |
| project typography | `selected_theme_text_styles`, `static_style_for_call` | normalized Text properties plus verified fonts | unique project theme overrides Material3 defaults; ambiguous providers fail; direct Text arguments override style |
| opacity/zIndex | resolved draw values | opacity/zIndex branches | emitted as draw properties |
| unsupported type/modifier | required fact or unresolved entry | final gate | must fail, never implicit Stack or source fallback |

## Common Primitive Scope

`PullToRefreshBox` is the AndroidX Material3 container, not a third-party widget.
The source step records `isRefreshing` as `migration.style.state.refreshing` in the
single `version_json.json`. Select its boolean value in the scene inputs, including
an explicit symbol binding when it comes from remembered local state. An unknown
value remains unresolved; the preview keeps the content but does not invent a
refreshing state. The generated Stack keeps all Compose BoxScope children in
source order and applies content alignment there. Do not substitute ArkUI `Refresh`:
its default refreshing state moves the content by 64vp, unlike Compose's overlay.
At the settled refreshing state, Material3 uses a 40dp indicator container, a 16dp
spinner, and an 80dp threshold (container top = 40dp). The target uses a native
`LoadingProgress` overlay with these sizes and resolved theme colors; its animation
and shadow are not claimed pixel-identical. No network callback, refresh gesture,
timer, or fake completion is generated.
Business refresh handling must be connected separately. Custom `indicator` and
pull-distance `state` require separate mappings and do not pass the visual gate.

The single-JSON path additionally accepts Checkbox, Switch, RadioButton, discrete Slider,
determinate LinearProgressIndicator/CircularProgressIndicator, and horizontal/vertical Divider.
Their constants are parsed once by `page_native_controls.py`, validated by required facts,
and consumed through native ArkUI attributes. Checkbox explicitly uses a rounded-square shape.
Selection primitives clear Harmony's implicit margin/padding before applying source spacing.
This is native primitive UI/state support, not a claim that complete Material themes, colors
objects, slots, or business callbacks have been reconstructed.

Slider preserves min/max and converts positive Compose steps into `(max-min)/(steps+1)`.
ArkUI has a minimum native step of 0.01; a continuous source Slider is explicitly rejected,
not discretized behind the caller's back. Missing progress is rejected rather than converted
to a fixed percentage. Custom thumb/track, gapSize/strokeCap/stop indicators and divider
startIndent fail until they have a dedicated renderer. A progress track color and an outer
modifier background cannot both be consumed through one backgroundColor attribute.

Text softWrap=false is supported for one paragraph without hard newlines. minLines=1 is the
native minimum. Greater Text minLines uses the verified target font's measured ascent/descent,
requested inter-line spacing and source padding, not a reference frame height. Conflicting
height constraints, unverified fonts, and input-field minimum lines greater than one fail.

Removed paths: bbox-derived flow margins and missing-offset translation inference. Parent
fraction offsets no longer freeze reference parent dimensions. Measurement observers shared
with border drawing use one callback; source padding is subtracted from the measured scope.
An unbounded scrolling axis cannot be substituted with its content's measured height.

Supported Material3 outlined decoration retains the editor minimum/content padding and a separate
supporting-text slot, including space reserved by an empty non-null lambda. This does not imply
support for every Material version, floating label, error or arbitrary decoration combination.

Not in automatic scope: full Material input decoration/label/error slots; arbitrary
ConstraintLayout graphs; weight(fill=false); interleaved measure/draw modifier chains;
complex brushes; Pager/Grid/Dialog and arbitrary native defaults. These must remain explicit
unsupported facts/types, not an alternative source-reader fallback or an implicit Stack.
The existing elevation-to-shadow approximation remains labelled approximate; it is not
promoted to an exact mapping by a passing field-consumption test.

The older `test_tools.py` source-translator success cases still invoke the retired CLI without
`--page-json`. They are not current single-input coverage. Do not restore that API or silently
skip those failures and report the entire repository green; the current entry has independent
source/JSON/renderer tests, and the retired cases need a separate test-suite migration.

`bbox` means a geometric bounding rectangle, not the Compose `Box` component.
Box children use native Stack alignment. Reference rectangles may be used by
diagnostics, but a missing offset rule must not be repaired by subtracting a
predicted alignment origin from a child rectangle.

## Gates

`build_target_phase_consumption_gate` requires exact component-instance and field
paths. A component frame, a rendered source call, or another instance of that call
does not prove consumption. Symbolic facts cannot pass even when a matching field
path was recorded. Structural checks require the corresponding node/children.
Unsupported facts do not stop candidate artifact generation. Both JSON and ArkUI commands
exit zero after writing outputs; ArkUI reports `ok=true` for that operation only. Partial
results retain `generation_complete=false`, `verdict=fail`, and component/path/expression
records, including failures from the upstream phase gate. Unsupported controls are omitted
rather than replaced with guessed UI; unknown text is explicitly null/unresolved. In this
document, unsupported/failed means completeness fails, not that all output is suppressed.
Malformed trees, ambiguous page state, unsafe assets and ownership violations remain fatal.

Consumption is evidence of an emitter branch, not pixel equivalence. The separate
runtime test must verify bounds, scrolling, font resources and screenshots. A
Pillow/SSIM comparison may still fail after all field gates pass. Geometry marked
`source_inferred` or `unresolved` is not promoted to measured runtime geometry.

### Stability Checks

Keep syntax selection separate from framework API adapters. `evaluate_expression`
and modifier projection share `LayoutExpressions` over Kotlin PSI for references,
if/when, operators, nullable access and selected state. `evaluate_value_leaf` only
handles bounded literals/framework calls; it must not reintroduce a second
string-based control-flow evaluator. Unknown branches stay unresolved, not false.
This is not full Kotlin compiler symbol/type analysis or arbitrary function execution.

TextStyle constructors, selected theme styles and nested `copy` calls project each
property through the same scoped resolver. Direct Text parameters take precedence.
An unknown property must retain a field-level diagnostic without discarding the
Text node or unrelated known properties. Test both selected branches and unknown
values; verify the generated color at the native text region, not only in JSON.

Run `test_fixed_state_value_parity` to compare value and modifier paths using the
same state, nested parameters and equivalent syntax. Run `test_material_home_containers`
for container preservation and measured-layout emitter regressions. Those Python
tests prove parsing/emission, **not** target layout correctness.

For a renderer change, also regenerate unchanged real-page inputs in the affected
project and at least one previous project. Install the new output and capture its
runtime tree at a bound viewport/font scale. Assert component presence, sibling
geometry and source padding, not just screenshot count or emitted API names.
Record emulator and physical-device evidence separately; never label an emulator
run as a physical-device pass. Do not hand-adjust generated page layouts.

Example regression: a default vertical Divider in a Row with IntrinsicSize.Min
must contribute zero to the initial cross-axis measurement, then stretch to the
content height. ArkUI `height('auto')` still fills the available constraint here;
use zero height plus Stretch only for this cross-axis context. Explicit divider
sizes must remain unchanged. The device assertion compares divider top/bottom to
the actual sibling content and verifies the Row's source padding. A loose height
threshold alone is not sufficient. Horizontal scrolling content must likewise
wrap its cross-axis height rather than receive an unconditional 100% height.
On the scrolling axis, Compose fillMaxWidth/Height is a no-op when the incoming
maximum is unbounded. Walk the source ancestor constraints rather than using the
viewport as that maximum. An intervening explicit size or maximum constraint
restores a finite limit; test that path separately. This must not alter Box
matchParentSize, which has a different measurement contract.

Reference frames must not become fixed/minimum dimensions for content-sized Text,
Row/Column or project wrappers. Explicit source sizes and constraints are retained;
absent Text dimensions use native text measurement. A wrapper forwards declared
fill/weight rules structurally, not by matching its reference frame to its child.
Material3 button minimum width (58dp), touch minimum (48dp), and small app-bar content height (64dp) are
framework defaults, not frame-derived estimates. RelativeContainer wrap uses
native auto sizing; a redundant zero origin anchor is omitted only when there is
no opposite/center anchor in that axis. This does not cover every ConstraintLayout
cycle or intrinsic modifier combination.

## Layout Expression Projection

`kotlin_psi.py` invokes the pinned Kotlin compiler PSI parser, without loading or executing
application classes. `layout_expressions.py` resolves per-instance parameters and aliases,
selects fixed-state branches, then produces one ordered modifier chain. Both style extraction
and layout-rule normalization consume that selected chain. Row/Column/Box alignment and
arrangement arguments use the same scope and expression tree. `syntax_expression` and local
bindings retain original newlines; display-normalized summaries are not reparsed as Kotlin.
Named project slots are serialized explicitly and keep their expanded native children, even
when the owning component also contains unsupported drawing.

This is expression-level syntax parsing, not a complete Kotlin project/type/overload resolver.
The existing component inventory, framework API adapters and page-state catalog still have
their documented boundaries. Unknown extension functions, unresolved values/cycles, and
unsupported modifier operations remain recorded; no source fallback runs in ArkUI. In
particular, selecting a drawing expression does not implement its Canvas output. Passing
expression/consumption tests does not imply complete visual acceptance.

See [setup and dependency versions](source-page-workflow.md#layout-expression-parser-setup).

Image resource dimensions are preferences, not fixed control dimensions. Modifier
`size`/`width`/`height` facts belong to `style.layout`, even for Image/Icon/AsyncImage.
Old page JSON that stores modifier size requirements in `style.asset` must be
regenerated; it cannot be silently interpreted as an intrinsic-size image. Source
reference frames also constrain intrinsic images inside their overlay parent,
while actual target sizes are measured natively rather than copied from those frames.

Shadow blur and offsets in page JSON use logical dp. ArkUI `ShadowOptions`
expects physical px for all three fields, so the draw emitter calls
`this.getUIContext().vp2px` at runtime; it must not bake in the reference density.
This unit conversion does not prove that Android elevation/ambient/spot lighting
is equivalent to a single blur shadow. The current elevation approximation still
needs separate validation and must not be described as exact shadow reconstruction.

Compose layout dimensions and padding are rounded to physical pixels at runtime,
using the target density rather than the reference density. Border strokes use
the Compose ceil/hairline rule and a measured decorative overlay, so drawing a
border does not add ArkUI border insets to the content measurement. The overlay
uses its owning component's measured size, not percentage sizing against the window.
An explicit clip emits `clip(true)` independently of corner radius.

For verified font assets, Compose Text uses whole-pixel hinted glyph sizing and
retains the unquantized font's ascent/descent for its minimum natural line box.
Requested line height is consumed as spacing between lines; it is not extra
padding above/below a single line. Explicit text height/constraints are not
overridden. Native text measurement still determines width and wrapping; no
text-length estimates or reference-frame widths are used. The Banking regression
checks 12/14/16sp at density 2.9 and short/long text. This is not proof for every
font, fallback script, explicit LineHeightStyle or platformStyle combination.

AsyncImage consumes a resolved HTTP(S) model URL directly. A debug/preview
placeholder is not a populated runtime image. Unresolvable local resources and
malformed model URLs remain unresolved rather than producing a guessed asset.

## Regression

Run the current single-input suite:

```bash
PYTHONPATH="$SKILL_ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 -B -m unittest \
  test_layout_mapping_contract test_generate_lanhu_source_page \
  test_generate_arkui_lanhu_input test_real_page_pipeline \
  test_surface_padding test_input_decoration_layout test_static_ui_preservation
```

`test_layout_mapping_contract.py` covers exact field failure, repeated-call
isolation, width/height overloads, fractions, constraints, weight ratios,
unsupported fill=false, child alignment, nested scroll, retained offscreen
children, Material3 bar height, project typography precedence, and verified font bytes.
Reference-frame perturbation tests cover text, multi-child buttons and project
wrappers. Runtime checks must also exercise long text growing its parent and
moving later siblings, explicit-size preservation, and nested stretch surfaces.

The older `test_tools.py` source-translation cases still invoke the removed CLI.
Their results must not be reported as single-input coverage, and the old CLI must
not be restored merely to make them green. Those fixtures need an explicit
migration to source-inventory -> version_json -> renderer tests.
