package dev.ets

// Matrix filtering uses unpremultiplied, normalized colors. SrcIn replaces RGB
// with constant tint channels and multiplies alpha; the renderer premultiplies afterward.
internal val imageTintSupport = listOf("""
function __etsImageTint(color: number): ColorFilter {
  return new ColorFilter([
    0, 0, 0, 0, ((color >>> 16) & 255) / 255,
    0, 0, 0, 0, ((color >>> 8) & 255) / 255,
    0, 0, 0, 0, (color & 255) / 255,
    0, 0, 0, (color >>> 24) / 255, 0
  ]);
}

function __etsOptionalImageFilter(filter: ColorFilter | null): ColorFilter {
  return filter ?? new ColorFilter([
    1, 0, 0, 0, 0,
    0, 1, 0, 0, 0,
    0, 0, 1, 0, 0,
    0, 0, 0, 1, 0
  ]);
}
""".trimIndent())
