package dimensionvalues

import androidx.compose.ui.unit.*

fun dp(value: Double): Dp = value.dp
fun sp(value: Int): TextUnit = value.sp
fun read(value: Dp): Float = value.value
fun font(value: TextUnit): Float = value.value
fun fractional(value: Double): Float = value.sp.value
fun observations(): List<Double> = listOf(
    read(dp(16.0)).toDouble(), read(dp(0.1)).toDouble(),
    read(dp(16777217.0)).toDouble(), font(sp(18)).toDouble(),
    font(sp(16777217)).toDouble(), fractional(0.1).toDouble(),
    fractional(-2.25).toDouble()
)
