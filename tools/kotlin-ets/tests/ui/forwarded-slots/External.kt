package demo.adapters

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
external fun Frame(label: String, modifier: Modifier, content: @Composable () -> Unit)

@Composable
fun Relay(content: @Composable () -> Unit) {
    Frame("External frame", Modifier, content)
}

@Composable
fun ExternalPage() { Relay { Text("External content") } }
