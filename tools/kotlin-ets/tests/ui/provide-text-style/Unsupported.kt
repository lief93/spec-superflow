package providetextstyle

import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle

@Composable
fun UnsupportedPage() {
    ProvideTextStyle(TextStyle(background = Color.Red)) { Text("Unsupported") }
}
