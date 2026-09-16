package modifierarguments
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign

@Composable
fun BadDefault(modifier: Modifier, alignment: TextAlign = TextAlign.Left) {}
