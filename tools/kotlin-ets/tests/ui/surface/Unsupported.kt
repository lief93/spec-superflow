package surface

import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.width
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable fun DefaultBackground() { Surface(contentColor = Color.White) { Text("Missing theme") } }
@Composable fun DefaultContentColor() { Surface(color = Color.Black) { Text("Missing theme") } }
@Composable fun Elevated() {
    Surface(color = Color.Black, contentColor = Color.White, tonalElevation = 2.dp) { Text("Elevated") }
}
@Composable fun Interactive() {
    Surface(onClick = {}, color = Color.Black, contentColor = Color.White) { Text("Interactive") }
}
private var count = 0
private fun nextColor(): Color { count += 1; return Color.Black }
@Composable fun Effectful() {
    Surface(color = nextColor(), contentColor = nextColor()) { Text("Order") }
}

private var argb = 0
private fun nextWidth(): Int { argb = -65536; return 80 }
@Composable fun MutableColor() {
    Surface(modifier = Modifier.width(nextWidth().dp), color = Color.Black,
        contentColor = Color(argb)) { Text("Order") }
}
