package materialtext

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.sp

@Composable
fun ButtonFrame(content: @Composable () -> Unit) {
    Button(onClick = {}) { content() }
}

@Composable
fun ButtonLabel() { Text("Wrapped label") }

@Composable
fun MaterialText() {
    Column {
        Text("Body")
        Text("Large body", fontSize = 24.sp)
        ButtonFrame {
            ButtonLabel()
            Text("Explicit label", fontSize = 16.sp)
        }
        Text("Body restored")
    }
}
