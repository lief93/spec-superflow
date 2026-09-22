package colorcopy

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Column
import androidx.compose.ui.graphics.Color

fun unchanged(color: Color): Color = color.copy()

fun alphaOnly(color: Color, alpha: Float): Color = color.copy(alpha = alpha)

fun reordered(color: Color, red: Float, green: Float, blue: Float, alpha: Float): Color =
    color.copy(blue = blue, alpha = alpha, red = red, green = green)

class ChannelCounter {
    var next: Int = 0
    fun take(): Float {
        val value = next
        next = next + 1
        return value / 10f
    }
}

fun reorderedEffects(color: Color): Color {
    val counter = ChannelCounter()
    return color.copy(blue = counter.take(), alpha = counter.take(),
        red = counter.take(), green = counter.take())
}

@Composable
fun Page() {
    val base = Color(0x80402010)
    Column {
        Text("Default", color = unchanged(base))
        Text("Alpha", color = alphaOnly(base, 0.25f))
        Text("Named", color = reordered(base, 0.1f, 0.2f, 0.3f, 0.25f))
        Text("Evaluation order", color = reorderedEffects(base))
        Text("Static", color = base.copy(alpha = 0.25f, blue = 0.75f))
    }
}
