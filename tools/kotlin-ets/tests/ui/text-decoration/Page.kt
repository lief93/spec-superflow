package decoration
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.sp

fun underline(): TextStyle = TextStyle(textDecoration = TextDecoration.Underline, color = Color.Red, fontSize = 24.sp)
@Composable fun Page() {
    Column {
        Text("Underline", style = underline())
        Text("No line", style = underline(), textDecoration = TextDecoration.None)
        Text("Strike", style = underline(), textDecoration = TextDecoration.LineThrough, color = Color.Blue)
    }
}
@Composable fun Combined() { Text("Both", textDecoration = TextDecoration.Underline + TextDecoration.LineThrough) }
