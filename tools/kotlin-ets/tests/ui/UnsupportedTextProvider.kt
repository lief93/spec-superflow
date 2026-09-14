package negative

import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.sp

@Composable
fun UnknownPage() {
    ProvideTextStyle(TextStyle(lineHeight = 32.sp)) { Text("Custom") }
}
