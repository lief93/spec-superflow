package dimensionvalues

import androidx.compose.ui.unit.*

class Spacing(val value: Dp = Dp.Unspecified)

fun dp(value: Double): Dp = value.dp
fun sp(value: Int): TextUnit = value.sp
fun read(value: Dp): Float = value.value
fun font(value: TextUnit): Float = value.value
fun fractional(value: Double): Float = value.sp.value
fun resolved(value: Dp = Dp.Unspecified, fallback: Dp = 0.dp): Dp =
    if (value == Dp.Unspecified) fallback else value

var dimensionReads = 0
fun nextUnspecified(): Dp { dimensionReads += 1; return Dp.Unspecified }
fun consumeUnspecified(): Float = nextUnspecified().value
fun currentDimensionReads(): Int = dimensionReads

fun observations(): List<Double> = listOf(
    read(dp(16.0)).toDouble(), read(dp(0.1)).toDouble(),
    read(dp(16777217.0)).toDouble(), font(sp(18)).toDouble(),
    font(sp(16777217)).toDouble(), fractional(0.1).toDouble(),
    fractional(-2.25).toDouble(), resolved().value.toDouble(),
    resolved(Dp.Unspecified, 6.dp).value.toDouble(),
    resolved(if (read(1.dp) == 1f) 3.dp else Dp.Unspecified).value.toDouble(),
    resolved(Spacing().value, 4.dp).value.toDouble(),
    if (0.dp == Dp.Unspecified) 1.0 else 0.0,
    if (Dp.Unspecified == Dp.Unspecified) 1.0 else 0.0,
)
