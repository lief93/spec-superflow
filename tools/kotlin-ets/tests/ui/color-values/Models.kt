package colorvalues

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb

class Palette(val foreground: Color)

class OptionalPalette(val foreground: Color = Color.Unspecified)

fun selectColor(page: Int, primary: Color, secondary: Color): Color = when (page) {
    0 -> primary
    1 -> secondary
    else -> Color.Transparent
}

fun fromArgb(argb: Int): Color = Color(argb)

fun resolved(color: Color = Color.Unspecified, fallback: Color = Color.Black): Color =
    if (color == Color.Unspecified) fallback else color

fun observations(): List<Int> = listOf(
    selectColor(0, Palette(Color.White).foreground, Color.Black).toArgb(),
    selectColor(1, Color.White, Color(0x80123456)).toArgb(),
    selectColor(2, Color.White, Color.Red).toArgb(),
    fromArgb(-1).toArgb(),
    fromArgb(Int.MIN_VALUE).toArgb(),
    fromArgb(0x123456).toArgb(),
    Color(0x7FFFFFFF12345678L).toArgb(),
    resolved().toArgb(),
    resolved(Color.Unspecified, Color.White).toArgb(),
    resolved(if (fromArgb(1).toArgb() == 1) Color.Red else Color.Blue).toArgb(),
    resolved(OptionalPalette().foreground, Color.Green).toArgb(),
)
