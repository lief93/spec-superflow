package ownership

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
private fun PrivateCaption(label: String) { Text(label) }

@Composable
fun Leaf(label: String) { PrivateCaption(label) }

@Composable
fun Chain(label: String) { Leaf(label) }

@Composable
fun Action(label: String, onAction: () -> Unit) {
    Button(onClick = onAction) { Text(label) }
}

@Composable
fun Frame(content: @Composable () -> Unit) { Column { content() } }

@Composable
fun Bridged(label: String) {
    val captured = label + "!"
    Frame { Leaf(captured) }
}

@Composable
fun Dependent(label: String) { Bridged(label) }

@Composable
fun DeepDependent(label: String) { Dependent(label) }
