package surfaceelevation

import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.surfaceColorAtElevation
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Composable
fun Page(elevation: Dp = 2.dp) {
    val colors = lightColorScheme(surface = Color(0x80402010), surfaceTint = Color(0xC0E08040))
    Text("Elevated", color = colors.surfaceColorAtElevation(elevation))
}
