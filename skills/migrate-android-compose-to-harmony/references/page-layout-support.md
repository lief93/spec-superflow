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
| Project component | expanded internal tree and slot ownership | `page_snapshot_component_lines` | retain the expanded children; unsupported composition remains unresolved, not a blanket one-child rule |
| ConstraintLayout | normalized link/center relationships | `page_snapshot_constraint_alignment_lines` | only declared supported anchors; no guessed positions |
| size(width,height) | `size_arguments`, `static_style_for_call` | `page_snapshot_dimension_lines` | positional/named constant dp values |
| image intrinsic size | `style.asset.width_dp/height_dp`, separate from modifier sizes in `style.layout` | `page_snapshot_intrinsic_image_lines` | Fit/Inside uses native bounded measurement and aspect ratio; explicit sizes/fill still take precedence; unverified intrinsic scaling modes fail |
| fillMaxWidth/Height/Size | `normalized_layout_rules` | `page_snapshot_dimension_lines` | constant fractions; unknown fraction remains unresolved |
| wrapContent/intrinsic | `normalized_layout_rules` | `page_snapshot_dimension_lines`, `page_snapshot_stretched_axis` | native content measurement and full cross-axis stretch, including single-root project wrappers; unsupported intrinsic fill axes/fractions fail |
| weight | ratio and fill in layoutRules | `page_snapshot_source_layout_weight` | native layoutWeight for fill=true; fill=false fails explicitly |
| widthIn/heightIn/sizeIn | min/max constraints in layoutRules | constraintSize branch | constant nonnegative bounds; min must not exceed max |
| child align | Alignment enum in layoutRules | alignSelf/align branch | Row/Column cross-axis or Stack nine-way alignment |
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

Reference frames must not become fixed/minimum dimensions for content-sized Text,
Row/Column or project wrappers. Explicit source sizes and constraints are retained;
absent Text dimensions use native text measurement. A wrapper forwards declared
fill/weight rules structurally, not by matching its reference frame to its child.
Material button touch minimum (48dp) and small app-bar content height (64dp) are
framework defaults, not frame-derived estimates. RelativeContainer wrap uses
native auto sizing; a redundant zero origin anchor is omitted only when there is
no opposite/center anchor in that axis. This does not cover every ConstraintLayout
cycle or intrinsic modifier combination.

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
