package materialbutton
import androidx.compose.material3.ButtonColors
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.ui.unit.dp

var count = 0
fun next(): Color { count += 1; return Color(count) }
fun palette(): ButtonColors = ButtonColors(next(), next(), next(), next())
fun observations(): List<Int> {
    val value = palette()
    return listOf(value.containerColor.toArgb(), value.contentColor.toArgb(),
        value.disabledContainerColor.toArgb(), value.disabledContentColor.toArgb(), count)
}
fun nextSize(): androidx.compose.ui.unit.Dp { count += 1; return count.dp }
fun edges(): PaddingValues = PaddingValues(start = nextSize(), top = nextSize(), end = nextSize(), bottom = nextSize())
fun uniform(): PaddingValues = PaddingValues(nextSize())
