package materialtheme

import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.contentColorFor
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.takeOrElse
import androidx.compose.ui.graphics.toArgb

fun main() {
    val scheme = lightColorScheme()
    val backgrounds = listOf(scheme.primary, scheme.secondary, scheme.tertiary, scheme.background,
        scheme.error, scheme.primaryContainer, scheme.secondaryContainer, scheme.tertiaryContainer,
        scheme.errorContainer, scheme.inverseSurface, scheme.surface, scheme.surfaceVariant,
        scheme.surfaceBright, scheme.surfaceContainer, scheme.surfaceContainerHigh,
        scheme.surfaceContainerHighest, scheme.surfaceContainerLow, scheme.surfaceContainerLowest,
        Color(0xFF010203))
    backgrounds.forEach { println(scheme.contentColorFor(it).takeOrElse { Color.Cyan }.toArgb()) }
    val collision = lightColorScheme(primary = Color.Red, surface = Color.Red, onPrimary = Color.Green, onSurface = Color.Blue)
    println(collision.contentColorFor(Color.Red).toArgb())
}
