package widgetsstate

import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue

@Composable
fun StateProfile() {
    var enabled by remember { mutableStateOf(false) }
    val count = remember { mutableStateOf(0) }
    val label = remember { mutableStateOf("ready") }

    Button(onClick = {
        enabled = !enabled
        count.value = count.value + 1
        label.value = if (enabled) "on" else "off"
    }) {
        Text(if (enabled) label.value else "disabled")
    }
}
