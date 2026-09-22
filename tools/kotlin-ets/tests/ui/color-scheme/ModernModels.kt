package colorschememodern

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb

private fun fixed(value: ColorScheme): List<Int> = listOf(
    value.primaryFixed.toArgb(), value.primaryFixedDim.toArgb(),
    value.onPrimaryFixed.toArgb(), value.onPrimaryFixedVariant.toArgb(),
    value.secondaryFixed.toArgb(), value.secondaryFixedDim.toArgb(),
    value.onSecondaryFixed.toArgb(), value.onSecondaryFixedVariant.toArgb(),
    value.tertiaryFixed.toArgb(), value.tertiaryFixedDim.toArgb(),
    value.onTertiaryFixed.toArgb(), value.onTertiaryFixedVariant.toArgb(),
)

fun modernLightDefaults(): List<Int> = fixed(lightColorScheme())
fun modernDarkDefaults(): List<Int> = fixed(darkColorScheme())

private var trace = 0
private fun traced(marker: Int, color: Color): Color { trace = trace * 10 + marker; return color }

fun modernOverrides(): List<Int> {
    trace = 0
    val light = lightColorScheme(traced(1, Color.Red), onPrimary = traced(2, Color.Green),
        primaryFixed = traced(3, Color.Blue))
    val dark = darkColorScheme(primary = traced(4, Color.Yellow), secondaryFixed = traced(5, Color.Cyan))
    return listOf(light.primary.toArgb(), light.onPrimary.toArgb(), light.primaryFixed.toArgb(),
        light.surfaceTint.toArgb(), dark.primary.toArgb(), dark.secondaryFixed.toArgb(),
        dark.surfaceTint.toArgb(), trace)
}
