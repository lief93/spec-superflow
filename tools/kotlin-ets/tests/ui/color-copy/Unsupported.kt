package colorcopy.unsupported

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.colorspace.ColorSpaces

@Composable
fun Page() {
    val wide = Color(0.1f, 0.2f, 0.3f, 1f, ColorSpaces.DisplayP3)
    Text("Wide", color = wide.copy(alpha = 0.5f))
}
