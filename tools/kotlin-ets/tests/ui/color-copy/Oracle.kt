package colorcopy

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb

private fun Color.hex(): String = toArgb().toUInt().toString(16).padStart(8, '0')

private class ChannelCounter {
    var next: Int = 0
    fun take(): Float = next++ / 10f
}

fun main() {
    val base = Color(0x80402010.toInt())
    println(base.copy().hex())
    println(base.copy(alpha = 0.25f).hex())
    println(base.copy(blue = 0.3f, alpha = 0.25f, red = 0.1f, green = 0.2f).hex())
    println(base.copy(red = -1f, green = 2f, blue = Float.NaN, alpha = 1.5f).hex())
    val counter = ChannelCounter()
    println(base.copy(blue = counter.take(), alpha = counter.take(),
        red = counter.take(), green = counter.take()).hex())
}
