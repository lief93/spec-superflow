package surfaceelevation.unsupported

import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.surfaceColorAtElevation
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.Dp

@Composable
fun Page() {
    Text("Unsupported", color = lightColorScheme().surfaceColorAtElevation(Dp.Unspecified))
}
