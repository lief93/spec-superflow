# Compose images through the typed backend

Image and Icon have separate rule files under `src/ui/controls`. Their values
use the ordinary API adaptation contract: `CallRule.mapType` maps the source
Painter representation to target Resource, and `painterResource` returns that
type through the shared call-result checker. A void result is still rejected.
The backend registers ImageResources once; rules do not parse Kotlin text or
call the old JSON page renderer.

## Materialize, compile, install resources

```sh
node tools/kotlin-ets/image-resources.mjs \
  --res-dir /path/android/module/src/main/res \
  --namespace example.app --out /tmp/new-image-assets

bash tools/kotlin-ets/kotlin-ets \
  --project /path/android --module :app --variant debug \
  --entry example.app.Page --out /tmp/new-page/Page.ets \
  --image-resources /tmp/new-image-assets/image-resources.properties
```

The properties file is an asset-symbol index, not a page snapshot or program IR.
Its adjacent `media` directory must exist. Both direct-source and Gradle-project
entry points accept the same flag. Resources are not inferred from integer IDs.
Missing R symbols or missing media fail rather than producing empty Stack nodes.

Install the produced media files, retaining their filenames, into the destination
module's `src/main/resources/base/media`. This is separate from the generated
page's directory. The compiler does not automatically alter the destination
project or copy files over its resources. See [asset materialization](image-resources.md)
for the supported formats, variant restrictions and no-overwrite policy.

## Bounded support

- Image's Painter overload: contentDescription, modifier, alpha, and Fit/Crop/
  FillBounds/Inside/None ContentScale. Default fitting is Contain. Other explicit
  arguments, including alignment and colorFilter, reject.
- Icon's Painter overload: explicit ARGB tint or Color.Unspecified. Default
  LocalContentColor is not guessed. ImageVector, ImageBitmap and arbitrary
  custom Painter implementations are not converted by this increment.
- Painter parameters and source helper-method boundaries are preserved. A
  conditional R resource stays conditional in generated ETS, not a preview value.
- Coil 2 AsyncImage accepts literal HTTP(S) model URLs without credentials,
  contentDescription, modifier, alpha and the same ContentScale subset. It
  becomes native Image URL loading, not a port of Coil. Request objects, dynamic
  models, custom loaders, placeholders and callbacks reject. The application
  must configure target networking permissions/policy; no network fetch is made
  during compilation and no network/device rendering was tested here.
- Resource IDs must retain resolved static R fields. Numeric/inlined IDs and
  resource-ID parameters without a symbolic binding are rejected. Namespace
  binding is explicit in the materializer, not inferred from a field's name.
- Non-null description expressions and literal null are supported. Arbitrary
  nullable expressions require explicit branches. Null marks decorative images
  inaccessible; descriptions become accessibilityText.
- Stable `Modifier.size(dp)` and `size(width, height)` use the existing ordered
  modifier lowering. Effectful dimensions reject rather than execute twice.
  Tests use explicit logical dimensions; density-sensitive intrinsic sizing and
  default icon sizing are not established as cross-platform equivalents.

Icon tint uses a SrcIn color matrix, not SVG-only fillColor. The matrix supplies
constant unpremultiplied RGB and scales source alpha, leaving premultiplication
to rendering. Reference implementation evidence:
[OpenHarmony image matrix application](https://github.com/openharmony/arkui_ace_engine/blob/master/frameworks/core/components_ng/render/adapter/drawing_image.cpp),
[OpenHarmony Skia adapter](https://github.com/openharmony/graphic_graphic_2d/blob/master/rosen/modules/2d_graphics/src/drawing/engine_adapter/skia_adapter/skia_color_filter.cpp),
[Skia matrix filtering](https://github.com/google/skia/blob/main/src/effects/colorfilters/SkMatrixColorFilter.cpp).
The helper is emitted only when a typed dependency requires it; the tint
expression is evaluated once.

## Verification

```sh
node tools/kotlin-ets/tests/resources/run.mjs
bash tools/kotlin-ets/tests/ui/images.sh
node tools/kotlin-ets/tests/ui/images-cli.mjs /absolute/resource-test-run/res --sdk
```

The first test prints the generated resource-fixture location. The third uses
the public materializer, the public compiler and optionally the SDK with
unchanged generated ETS and media. Tests cover resource binding/condition flow,
method/parameter retention, source-linked failures, the shared void-result
rejection, registry validation and executed tint-matrix arithmetic.
SDK compilation is not a device or visual-equivalence test. Neither private
project readiness nor full image-loader compatibility is implied.

Latest evidence (2026-09-14):

- `tests/resources/.work/run-2u2Bqf/complete.json`: bitmap copy and independent
  decode, vector conversion and 15 negative resource cases.
- `$TMPDIR/kotlin-ets-images.5UFPH4`: typed image/resource flow, shared wrong-type
  rejection, registry checks, twelve source-linked negatives and tint arithmetic.
- `$TMPDIR/kotlin-ets-images-cli-jooQGO`: public materializer/compiler run;
  `/private/tmp/kotlin-ets-basic-controls-sdk-FhbsmP/result.json`: unchanged
  generated ETS plus media compiled into ABC/HAP. No install or visual run.
- `$TMPDIR/kotlin-ets-typed-ui.oH1I2K` and
  `$TMPDIR/kotlin-ets-basic-controls.AYEPmh`: shared UI and basic-control regression.
