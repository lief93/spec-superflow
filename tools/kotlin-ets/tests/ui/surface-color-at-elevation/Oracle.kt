package surfaceelevation

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.dp

private fun hex(color: Color): String = color.toArgb().toUInt().toString(16).padStart(8, '0')

fun main() {
    val cases = listOf(
        Triple(0xFF203040, 0xFFE08020, 0f),
        Triple(0xFF203040, 0xFFE08020, -0f),
        Triple(0xFF203040, 0xFFE08020, 2f),
        Triple(0xFF203040, 0xFFE08020, 8f),
        Triple(0x80402010, 0xC0E08040, 2f),
        Triple(0x80402010, 0xC0E08040, 24f),
        Triple(0x00000000, 0xFFFFFFFF, 2f),
    )
    for ((surface, tint, elevation) in cases) {
        println(hex(elevated(Color(surface.toLong()), Color(tint.toLong()), elevation.dp)))
    }
    resetEvaluationTrace()
    println(hex(orderedColor()))
    println(currentEvaluationTrace())
}
