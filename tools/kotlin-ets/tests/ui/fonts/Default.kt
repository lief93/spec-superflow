package fontfixtures

import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily

fun defaultFamily(): FontFamily = FontFamily.Default

@Composable fun DefaultPage() {
    Text("System default font", style = TextStyle(fontFamily = defaultFamily()))
}
