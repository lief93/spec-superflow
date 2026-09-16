package decoration
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
var order = 0
fun decoration(): TextDecoration { order = order * 10 + 1; return TextDecoration.Underline }
fun alignment(): TextAlign { order = order * 10 + 2; return TextAlign.Center }
fun height(): TextUnit { order = order * 10 + 3; return 30.sp }
fun effectStyle(): TextStyle {
    val result = TextStyle(textDecoration = decoration(), textAlign = alignment(), lineHeight = height())
    order = order * 10 + 4
    return result
}
@Composable fun EffectsPage() {
    Text("Effects", style = effectStyle(), textDecoration = decoration(), textAlign = alignment(), lineHeight = height())
}
