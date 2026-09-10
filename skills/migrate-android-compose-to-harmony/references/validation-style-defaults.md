# Visual Defaults Before Validation

ArkUI input loading now applies declared visual defaults after decoding the
Lanhu JSON and before validating its migration styles. This also handles existing
`version_json.json` files: rerun ArkUI generation, without rebuilding the contract
or source JSON solely for this change.

Valid values and valid adapter/token references are preserved. A malformed value
or a property recorded as unresolved uses its declared migration default. Null
without an unresolved/required-fact diagnostic remains intentionally unspecified.

Covered fields are declared in `ui_migration/contracts/style_defaults.py`:
colors/tint, typography, surface paint, padding/margins, transforms, text and
accessibility descriptions, and progress/slider values. Defaults include black
foreground, 16sp text, full opacity, zero translation/padding, no border/background,
and empty unresolved text. These are migration defaults, not Android observations.
Coupled line-count and control-range bounds are checked together.

Each substitution is listed in the ArkUI result and manifest `warnings` with
`kind: style_default_applied`, component ID, property path, original value,
expression, fallback, and diagnostics. Business-component variant warnings also
include their state identity. The full migration command forwards these warnings.
The input file and upstream analysis verdict are not rewritten; the full command
can still report partial generation when upstream analysis is incomplete, but a
defaulted visual property no longer prevents the ArkTS file from being emitted.

This is not a blanket exception handler: component/tree identity, geometry,
interaction/security state, resources/checksums, unknown schema fields and invalid
adapter reference contracts remain checked. No arbitrary business values or
missing resource paths are invented. Add explicit defaults and validation tests
for additional fields rather than suppressing every validation error.
