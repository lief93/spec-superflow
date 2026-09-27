package androidtoharmony.runtime

import android.os.Build
import android.util.Log
import android.util.Base64
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.TextUnitType
import java.util.Locale
import java.io.ByteArrayOutputStream
import java.util.zip.GZIPOutputStream
import org.json.JSONArray
import org.json.JSONObject


private const val MARKER = "ANDROID_THEME_FACTS_GZIP_BASE64:"
private const val TAG = "AndroidToHarmony"


@Composable
fun RuntimeThemeFactsProbe(themeId: String) {
    val colors = MaterialTheme.colorScheme
    val typography = MaterialTheme.typography
    val shapes = MaterialTheme.shapes
    val density = LocalDensity.current
    val layoutDirection = LocalLayoutDirection.current

    LaunchedEffect(
        themeId,
        colors,
        typography,
        shapes,
        density.density,
        density.fontScale,
        layoutDirection,
    ) {
        Log.i(
            TAG,
            MARKER + gzipBase64(themePayload(
                themeId = themeId,
                colors = colors,
                typography = typography,
                shapes = shapes,
                density = density.density,
                fontScale = density.fontScale,
                layoutDirection = layoutDirection,
            ).toString()),
        )
    }
}


private fun themePayload(
    themeId: String,
    colors: ColorScheme,
    typography: Typography,
    shapes: Shapes,
    density: Float,
    fontScale: Float,
    layoutDirection: LayoutDirection,
): JSONObject {
    val unresolved = JSONArray()
    val payload = JSONObject()
        .put("schema", "android-to-harmony.compose-theme-facts.v1")
        .put("platform", "android")
        .put("theme_id", themeId)
        .put(
            "capture",
            JSONObject()
                .put("sdk_int", Build.VERSION.SDK_INT)
                .put("density", density.toDouble())
                .put("font_scale", fontScale.toDouble())
                .put(
                    "layout_direction",
                    if (layoutDirection == LayoutDirection.Rtl) "rtl" else "ltr",
                ),
        )
        .put(
            "theme",
            JSONObject()
                .put("colors", colorSchemeJson(colors))
                .put("typography", typographyJson(typography, unresolved))
                .put("shapes", shapesJson(shapes)),
        )
        .put(
            "provenance",
            JSONArray().put(
                JSONObject()
                    .put(
                        "paths",
                        JSONArray()
                            .put("theme.colors")
                            .put("theme.typography")
                            .put("theme.shapes"),
                    )
                    .put("origin", "runtime")
                    .put("source", "MaterialTheme"),
            ),
        )
        .put("unresolved", unresolved)
    return payload
}


private fun colorSchemeJson(colors: ColorScheme): JSONObject = JSONObject()
    .put("primary", colorHex(colors.primary))
    .put("onPrimary", colorHex(colors.onPrimary))
    .put("primaryContainer", colorHex(colors.primaryContainer))
    .put("onPrimaryContainer", colorHex(colors.onPrimaryContainer))
    .put("inversePrimary", colorHex(colors.inversePrimary))
    .put("secondary", colorHex(colors.secondary))
    .put("onSecondary", colorHex(colors.onSecondary))
    .put("secondaryContainer", colorHex(colors.secondaryContainer))
    .put("onSecondaryContainer", colorHex(colors.onSecondaryContainer))
    .put("tertiary", colorHex(colors.tertiary))
    .put("onTertiary", colorHex(colors.onTertiary))
    .put("tertiaryContainer", colorHex(colors.tertiaryContainer))
    .put("onTertiaryContainer", colorHex(colors.onTertiaryContainer))
    .put("background", colorHex(colors.background))
    .put("onBackground", colorHex(colors.onBackground))
    .put("surface", colorHex(colors.surface))
    .put("onSurface", colorHex(colors.onSurface))
    .put("surfaceVariant", colorHex(colors.surfaceVariant))
    .put("onSurfaceVariant", colorHex(colors.onSurfaceVariant))
    .put("surfaceTint", colorHex(colors.surfaceTint))
    .put("inverseSurface", colorHex(colors.inverseSurface))
    .put("inverseOnSurface", colorHex(colors.inverseOnSurface))
    .put("error", colorHex(colors.error))
    .put("onError", colorHex(colors.onError))
    .put("errorContainer", colorHex(colors.errorContainer))
    .put("onErrorContainer", colorHex(colors.onErrorContainer))
    .put("outline", colorHex(colors.outline))
    .put("outlineVariant", colorHex(colors.outlineVariant))
    .put("scrim", colorHex(colors.scrim))
    .put("surfaceBright", colorHex(colors.surfaceBright))
    .put("surfaceDim", colorHex(colors.surfaceDim))
    .put("surfaceContainer", colorHex(colors.surfaceContainer))
    .put("surfaceContainerHigh", colorHex(colors.surfaceContainerHigh))
    .put("surfaceContainerHighest", colorHex(colors.surfaceContainerHighest))
    .put("surfaceContainerLow", colorHex(colors.surfaceContainerLow))
    .put("surfaceContainerLowest", colorHex(colors.surfaceContainerLowest))


private fun typographyJson(typography: Typography, unresolved: JSONArray): JSONObject = JSONObject()
    .put("displayLarge", textStyleJson("displayLarge", typography.displayLarge, unresolved))
    .put("displayMedium", textStyleJson("displayMedium", typography.displayMedium, unresolved))
    .put("displaySmall", textStyleJson("displaySmall", typography.displaySmall, unresolved))
    .put("headlineLarge", textStyleJson("headlineLarge", typography.headlineLarge, unresolved))
    .put("headlineMedium", textStyleJson("headlineMedium", typography.headlineMedium, unresolved))
    .put("headlineSmall", textStyleJson("headlineSmall", typography.headlineSmall, unresolved))
    .put("titleLarge", textStyleJson("titleLarge", typography.titleLarge, unresolved))
    .put("titleMedium", textStyleJson("titleMedium", typography.titleMedium, unresolved))
    .put("titleSmall", textStyleJson("titleSmall", typography.titleSmall, unresolved))
    .put("bodyLarge", textStyleJson("bodyLarge", typography.bodyLarge, unresolved))
    .put("bodyMedium", textStyleJson("bodyMedium", typography.bodyMedium, unresolved))
    .put("bodySmall", textStyleJson("bodySmall", typography.bodySmall, unresolved))
    .put("labelLarge", textStyleJson("labelLarge", typography.labelLarge, unresolved))
    .put("labelMedium", textStyleJson("labelMedium", typography.labelMedium, unresolved))
    .put("labelSmall", textStyleJson("labelSmall", typography.labelSmall, unresolved))


private fun textStyleJson(role: String, style: TextStyle, unresolved: JSONArray): JSONObject {
    if (style.fontFamily != null) {
        unresolved.put(
            JSONObject()
                .put("path", "theme.typography.$role.font_family")
                .put("expression", "runtime FontFamily")
                .put("reason", "runtime TextStyle does not expose the backing font asset"),
        )
    }
    return JSONObject()
        .put("font_size_sp", textUnitSp(style.fontSize))
        .put("font_weight", style.fontWeight?.weight ?: JSONObject.NULL)
        .put("font_style", style.fontStyle?.toString()?.lowercase(Locale.ROOT) ?: JSONObject.NULL)
        .put("font_family", JSONObject.NULL)
        .put("letter_spacing_sp", textUnitSp(style.letterSpacing))
        .put("line_height_sp", textUnitSp(style.lineHeight))
}


private fun shapesJson(shapes: Shapes): JSONObject = JSONObject()
    .put("extraSmall", shapeJson(shapes.extraSmall))
    .put("small", shapeJson(shapes.small))
    .put("medium", shapeJson(shapes.medium))
    .put("large", shapeJson(shapes.large))
    .put("extraLarge", shapeJson(shapes.extraLarge))


private fun shapeJson(shape: Any): JSONObject = JSONObject()
    .put("runtime_type", shape.javaClass.simpleName.ifBlank { "Shape" })
    .put("description", shape.toString())


private fun textUnitSp(value: TextUnit): Any =
    if (value.type == TextUnitType.Sp) value.value.toDouble() else JSONObject.NULL


private fun colorHex(color: Color): String =
    String.format(Locale.ROOT, "#%08X", color.toArgb())


private fun gzipBase64(value: String): String {
    val bytes = ByteArrayOutputStream()
    GZIPOutputStream(bytes).use { stream ->
        stream.write(value.toByteArray(Charsets.UTF_8))
    }
    return Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP)
}
