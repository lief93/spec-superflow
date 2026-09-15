package colorvalues

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

class ColorCounter(var count: Int = 0) {
    fun nextColor(): Color { count++; return Color.Red }
    fun label(): String = count.toString()
}

@Composable
fun EffectPage() {
    val counter = ColorCounter()
    Text(color = counter.nextColor(), text = counter.label())
}
