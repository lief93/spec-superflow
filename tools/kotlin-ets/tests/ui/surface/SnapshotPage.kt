package surface

import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private var argb = -1

@Composable private fun Content(color: Color) {
    Surface(color = Color.Black, contentColor = color) { Text("Snapshot") }
}

@Composable fun SnapshotPage() {
    val color = Color(argb)
    Content(color)
}
