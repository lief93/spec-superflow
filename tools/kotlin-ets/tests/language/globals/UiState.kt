package globals.ui

import androidx.compose.runtime.Composable
import androidx.compose.material3.Button
import androidx.compose.material3.Text

var counter: Int = 0

@Composable
fun Wrapper(content: @Composable () -> Unit) { content() }

@Composable
fun Controls() {
    Wrapper {
        Button(onClick = { counter++ }) { Text("Tap") }
    }
}
