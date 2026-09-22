package compositionlocal.unsupported

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.unit.Density

private val LocalDensity = staticCompositionLocalOf<Density> { error("missing") }

@Composable
fun UnsupportedPage() {
    Text(LocalDensity.current.toString())
}
