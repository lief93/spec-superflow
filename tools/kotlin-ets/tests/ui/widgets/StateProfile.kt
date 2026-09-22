package widgetsstate

import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue

interface StateModel {
    val name: String
}

@Composable
fun StateProfile(
    title: String,
    step: Int = 2,
    onState: (String) -> Unit,
    subtitle: String? = null,
    model: StateModel,
) {
    var enabled by remember { mutableStateOf(false) }
    val count = remember { mutableStateOf(0) }
    val label = remember { mutableStateOf("ready") }

    Button(onClick = {
        enabled = !enabled
        count.value = count.value + step
        label.value = if (enabled) "on" else "off"
        onState(label.value)
    }) {
        Text(if (enabled) "$title:${model.name}:${label.value}" else "disabled")
        Text(if (subtitle == null) "none" else subtitle)
    }
}
