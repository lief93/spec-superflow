# AndroidX Material3: `ColorScheme.surfaceColorAtElevation`

## Scope and pinned sources

The fixed Now in Android classpath used by this fixture contains Material3 **1.5.0-alpha03** and Compose UI Graphics **1.8.3**. The official [`material3-android-1.5.0-alpha03-sources.jar`](https://dl.google.com/dl/android/maven2/androidx/compose/material3/material3-android/1.5.0-alpha03/material3-android-1.5.0-alpha03-sources.jar) has SHA-256 `e7983f3907c0b7e13143751562bdfae3a5263f2e513bdd8531f32ebe12dd89f1`; its `commonMain/androidx/compose/material3/ColorScheme.kt` contains the formula below verbatim. The official [`ui-graphics-android-1.8.3-sources.jar`](https://dl.google.com/dl/android/maven2/androidx/compose/ui/ui-graphics-android/1.8.3/ui-graphics-android-1.8.3-sources.jar) has SHA-256 `d4703af7c49eccef50d4dc8184ae87367529ca5def06de16becd7bfc4757d9c4` and retains the source-over implementation described below.

The detailed cross-check uses the stable published AndroidX Material3 **1.3.2** implementation because the relevant function and Compose color behavior are unchanged, rather than relying on the moving `androidx-main` branch. The focused executable oracle itself runs against the fixed project's 1.5.0-alpha03/1.8.3 classpath.

Primary sources:

1. [Material3 1.3.2 Gradle module metadata](https://dl.google.com/dl/android/maven2/androidx/compose/material3/material3/1.3.2/material3-1.3.2.module) identifies the release and its published source archive. The archive entry is `material3-kotlin-1.3.2-sources.jar`, size 452,907 bytes, SHA-256 `28d908c089214f14e39cd63fe609a34ab246b4529f32c5197e2d6f4f57901e4d`.
2. [Material3 1.3.2 source archive](https://dl.google.com/dl/android/maven2/androidx/compose/material3/material3/1.3.2/material3-1.3.2-sources.jar), internal file `commonMain/androidx/compose/material3/ColorScheme.kt`, especially `ColorScheme.surfaceColorAtElevation` (archive lines 905-919), `ColorScheme.applyTonalElevation` (883-903), and `LocalColorScheme` / `LocalTonalElevationEnabled` (983-998). The same function is visible in the [official AndroidX mirror at pinned commit `a2b3a7a`](https://github.com/androidx/androidx/blob/a2b3a7a1a19ab9ca0431abe76a2dd956c061eb50/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/ColorScheme.kt#L917-L931).
3. [Material3 Desktop/JVM 1.3.2 binary](https://dl.google.com/dl/android/maven2/androidx/compose/material3/material3-desktop/1.3.2/material3-desktop-1.3.2.jar), symbol `ColorSchemeKt.surfaceColorAtElevation-3ABfNKs(ColorScheme, float)`. `javap -c -p` confirms the source formula and its JVM operation/property-read order.
4. [Compose UI Graphics 1.7.0 source archive](https://dl.google.com/dl/android/maven2/androidx/compose/ui/ui-graphics/1.7.0/ui-graphics-1.7.0-sources.jar), internal file `commonMain/androidx/compose/ui/graphics/Color.kt`, symbols `Color.copy`, `Color(...)`, `UncheckedColor(...)`, `Color.compositeOver`, and `compositeComponent`. The corresponding official mirror source is pinned at commit [`dcaa116`](https://github.com/androidx/androidx/blob/dcaa116fbfda77e64a319e1668056ce3b032469f/compose/ui/ui-graphics/src/commonMain/kotlin/androidx/compose/ui/graphics/Color.kt#L549-L581).
5. [Compose UI Unit 1.7.0 source archive](https://dl.google.com/dl/android/maven2/androidx/compose/ui/ui-unit/1.7.0/ui-unit-1.7.0-sources.jar), internal file `commonMain/androidx/compose/ui/unit/Dp.kt`, symbol `Dp`; and the [Desktop/JVM binary](https://dl.google.com/dl/android/maven2/androidx/compose/ui/ui-unit-desktop/1.7.0/ui-unit-desktop-1.7.0.jar), whose generated `Dp.equals-impl0(float, float)` uses `java.lang.Float.compare`.
6. [Compose UI Util 1.7.0 source archive](https://dl.google.com/dl/android/maven2/androidx/compose/ui/ui-util/1.7.0/ui-util-1.7.0-sources.jar), internal file `commonMain/androidx/compose/ui/util/MathHelpers.kt`, symbols `fastCoerceIn`, `fastCoerceAtLeast`, and `fastCoerceAtMost`.
7. [Kotlin language specification, pinned commit](https://github.com/Kotlin/kotlin-spec/blob/0f762a2314a9304e4b3fc386b1aceef1d56c7e4c/docs/src/md/kotlin.core/expressions.md#function-calls-and-property-access), “Function calls and property access”.

Material3 1.3.2 requests Foundation 1.7.0. The [Foundation Desktop 1.7.0 metadata](https://dl.google.com/dl/android/maven2/androidx/compose/foundation/foundation-desktop/1.7.0/foundation-desktop-1.7.0.module) in turn requests Compose UI 1.7.0, which is the dependency set used for the JVM observations below.

## Exact Material3 formula

The published function is a public, non-composable extension on a `ColorScheme` receiver:

```kotlin
@Stable
fun ColorScheme.surfaceColorAtElevation(elevation: Dp): Color {
    if (elevation == 0.dp) return surface
    val alpha = ((4.5f * ln(elevation.value + 1)) + 2f) / 100f
    return surfaceTint.copy(alpha = alpha).compositeOver(surface)
}
```

For every elevation that does not satisfy the zero test, the mathematical overlay alpha before `Color` packing is:

```text
alpha = (4.5 * ln(elevationDp + 1) + 2) / 100
```

This is evaluated from the runtime `Float` held by `Dp`; it is not a lookup table and it does not snap to Material elevation levels. On JVM, bytecode performs the `elevation + 1` addition as `float`, converts to `double` for `java.lang.Math.log`, converts the logarithm back to `float`, then performs the remaining multiply/add/divide as `float`.

The source tint's original alpha is discarded: `surfaceTint.copy(alpha = alpha)` replaces it. The result is then source-over composited onto `surface`.

## Zero, negative, unspecified, and infinite elevation

- `+0.0.dp` takes the early return and yields the receiver's packed `surface` value exactly. It does not read or composite `surfaceTint`.
- `-0.0.dp` does **not** take the early return on JVM. `Dp` is an inline value class over `Float`, and generated `Dp.equals-impl0` uses `Float.compare`; `Float.compare(-0.0f, +0.0f) != 0`. The logarithm sees `-0.0f + 1f == 1f`, so the pre-packing alpha is `0.02`.
- Negative values are not rejected. For `-1 < e < 0`, the formula is evaluated normally. It reaches alpha zero at `e = exp(-2 / 4.5) - 1`, approximately `-0.3588196.dp`; lower formula results are clamped to zero when `Color.copy` packs alpha.
- At exactly `-1.dp`, `ln(0)` produces negative infinity. Below `-1.dp`, it produces `NaN`. Compose UI 1.7.0's color packing clamps negative infinity to zero; `NaN` passes the comparison-based clamp and JVM float-to-int conversion packs it as zero. With ordinary valid colors, the transparent tint composite reconstructs the surface.
- `Dp.Unspecified` contains `Float.NaN`, so it follows that same `NaN` path on JVM and ordinarily yields the surface.
- Positive infinity produces positive-infinite alpha, which is clamped to `1`, so the result is the tint converted into the surface color space. Very large finite elevations likewise saturate once computed alpha reaches or exceeds `1`.

The invalid/negative-input outcomes after the Material3 formula depend on the Compose UI `Color` implementation present at runtime. The statements above are for the official 1.7.0 dependency path published with Material3 1.3.2. A lowering should reproduce the behavior contract intentionally rather than assuming the source formula itself rejects or clamps elevation.

## Compositing, color space, and rounding

`Color.compositeOver` implements non-premultiplied Porter-Duff source-over. It first converts the copied tint into the **surface/background color space**, then computes:

```text
outA = tintA + surfaceA * (1 - tintA)
outC = (tintC * tintA + surfaceC * surfaceA * (1 - tintA)) / outA
       (or 0 when outA == 0)
```

The result's color space is always the receiver scheme's `surface.colorSpace`. Component arithmetic occurs on the channel values in that destination color space; `compositeOver` does not separately linearize sRGB channels.

There are two packing/rounding stages relevant to exact parity:

1. `surfaceTint.copy(alpha = alpha)` calls the public `Color(...)` constructor while retaining the tint color space. It clamps alpha to `[0, 1]`. For sRGB, alpha and RGB are packed to 8-bit channels using `(component * 255 + 0.5f).toInt()`. For other supported color spaces, RGB uses IEEE-754 half precision and alpha uses 10 bits via `(alpha * 1023 + 0.5f).toInt()`.
2. `compositeOver` constructs the output through `UncheckedColor`. sRGB output channels are again rounded to 8 bits with `* 255 + 0.5f`; non-sRGB RGB channels are converted to half precision and alpha to 10 bits.

Therefore the final result is quantized, even though elevation feeds a continuous logarithm. A direct implementation that composites unquantized alpha, uses 32-bit ARGB arithmetic with a different rounding point, or ignores color-space conversion can differ by one or more channel values.

For an opaque sRGB surface the alpha simplifies to `1`, but the two packing stages still matter. For a translucent surface, the general alpha/component equations above must be preserved.

## Receiver and theme semantics

The function reads `surfaceTint` and `surface` from its explicit `ColorScheme` receiver. It contains no `MaterialTheme`, `CompositionLocal`, or `LocalTonalElevationEnabled` read and is not `@Composable`.

`MaterialTheme.colorScheme` is a composable getter whose [published implementation](https://github.com/androidx/androidx/blob/a2b3a7a1a19ab9ca0431abe76a2dd956c061eb50/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/MaterialTheme.kt#L73-L84) returns `LocalColorScheme.current`. Thus, in:

```kotlin
MaterialTheme.colorScheme.surfaceColorAtElevation(elevation)
```

the current theme lookup supplies the receiver at the call site; after that, the extension operates only on that captured scheme. An arbitrary stored/custom `ColorScheme` receiver must use that receiver's own `surface` and `surfaceTint`, regardless of the ambient theme.

`LocalTonalElevationEnabled` affects the separate internal `ColorScheme.applyTonalElevation` helper used by Material surfaces. It does not disable or alter a direct call to `surfaceColorAtElevation`.

## Evaluation order required by a lowering

The Kotlin specification requires evaluation of an explicit receiver first, followed by explicit arguments left-to-right in their source order, with each expression evaluated before invocation. An extension function is represented as a static JVM method, but that representation does not change source-level order.

For:

```kotlin
schemeExpression().surfaceColorAtElevation(elevationExpression())
```

a lowering must therefore:

1. evaluate `schemeExpression()` once;
2. evaluate `elevationExpression()` once;
3. invoke the equivalent operation with those captured values.

Inside the published JVM method, the order is: compare elevation with `+0.0.dp`; on equality read and return `surface`; otherwise compute alpha, read `surfaceTint`, perform `copy(alpha)`, then read `surface` and call `compositeOver`. The early return is observable as exact packed-color preservation and avoids the nonzero path's quantization/reconstruction.

For `MaterialTheme.colorScheme.surfaceColorAtElevation(elevationExpression())`, preserving receiver-first evaluation means reading the current composition-local color scheme before evaluating the elevation expression.

## Executable JVM observations

The published 1.3.2 Desktop/JVM method was invoked reflectively with official Compose UI/Runtime 1.7.0 artifacts, an opaque sRGB `surface = #FF202020`, and `surfaceTint = #FFFF0000`. These values exercise the real mangled method and packed `Color` implementation:

| elevation | packed ARGB result |
| ---: | --- |
| `+0.0.dp` | `FF202020` |
| `-0.0.dp` | `FF241F1F` |
| `1.dp` | `FF2B1E1E` |
| `3.dp` | `FF321D1D` |
| `6.dp` | `FF381D1D` |
| `-0.1.dp` | `FF231F1F` |
| `-0.36.dp` | `FF202020` |
| `-0.5.dp` | `FF202020` |
| `-1.dp` | `FF202020` |
| `-2.dp` | `FF202020` |
| `Dp.Infinity` | `FFFF0000` |
| `Dp.Unspecified` (`NaN`) | `FF202020` |

These observations are supporting evidence; the pinned published sources and binaries above define the behavior.
