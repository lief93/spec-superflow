package colorscheme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb

fun scheme(dark: Boolean): ColorScheme = if (dark) darkColorScheme() else lightColorScheme()
fun roles(value: ColorScheme): List<Int> = listOf(
    value.primary.toArgb(),
    value.onPrimary.toArgb(),
    value.primaryContainer.toArgb(),
    value.onPrimaryContainer.toArgb(),
    value.inversePrimary.toArgb(),
    value.secondary.toArgb(),
    value.onSecondary.toArgb(),
    value.secondaryContainer.toArgb(),
    value.onSecondaryContainer.toArgb(),
    value.tertiary.toArgb(),
    value.onTertiary.toArgb(),
    value.tertiaryContainer.toArgb(),
    value.onTertiaryContainer.toArgb(),
    value.background.toArgb(),
    value.onBackground.toArgb(),
    value.surface.toArgb(),
    value.onSurface.toArgb(),
    value.surfaceVariant.toArgb(),
    value.onSurfaceVariant.toArgb(),
    value.surfaceTint.toArgb(),
    value.inverseSurface.toArgb(),
    value.inverseOnSurface.toArgb(),
    value.error.toArgb(),
    value.onError.toArgb(),
    value.errorContainer.toArgb(),
    value.onErrorContainer.toArgb(),
    value.outline.toArgb(),
    value.outlineVariant.toArgb(),
    value.scrim.toArgb(),
    value.surfaceBright.toArgb(),
    value.surfaceContainer.toArgb(),
    value.surfaceContainerHigh.toArgb(),
    value.surfaceContainerHighest.toArgb(),
    value.surfaceContainerLow.toArgb(),
    value.surfaceContainerLowest.toArgb(),
    value.surfaceDim.toArgb()
)
private var reads = 0
private fun nextColor(): Color { reads += 1; return Color(reads) }
fun overrides(): List<Int> {
    reads = 0
    val value = lightColorScheme(secondary = nextColor(), primary = nextColor())
    val explicit = darkColorScheme(primary = Color.Red, surfaceTint = Color.Blue)
    return listOf(value.primary.toArgb(), value.secondary.toArgb(), value.surfaceTint.toArgb(),
        reads, explicit.primary.toArgb(), explicit.surfaceTint.toArgb())
}
