package forwardedslots

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun Frame(content: @Composable () -> Unit) {
    Button(onClick = {}) { content() }
}

@Composable
fun Relay(content: @Composable () -> Unit) { Frame(content) }

@Composable
fun Outer(content: @Composable () -> Unit) { Relay(content) }

@Composable
fun Page() {
    Column {
        Outer { Text("Forwarded label") }
        Text("Body restored")
    }
}
