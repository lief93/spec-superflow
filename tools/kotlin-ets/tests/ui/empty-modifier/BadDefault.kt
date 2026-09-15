package emptymodifier
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.style.TextAlign

@Composable
fun BadDefault(alignment: TextAlign = TextAlign.Left) {}
