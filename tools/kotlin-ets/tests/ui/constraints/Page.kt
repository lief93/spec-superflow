package constraints

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun Page() {
    val wide = remember { mutableStateOf(false) }
    val label = remember { mutableStateOf("Before") }
    Column {
        Constrained(if (wide.value) 240 else 120, label.value)
        Button(onClick = { wide.value = !wide.value }) { Text("Resize") }
        Button(onClick = { label.value = "After" }) { Text("Relabel") }
    }
}

@Composable
fun Constrained(width: Int, label: String, enableScroll: Boolean = false) {
    val scrollModifier = if (enableScroll) {
        Modifier.verticalScroll(rememberScrollState())
    } else {
        Modifier
    }
    BoxWithConstraints(Modifier.width(width.dp).height(100.dp).testTag("constraints")) {
        val availableWidth = maxWidth.value
        Column(Modifier.height(maxHeight).width(maxWidth).then(scrollModifier).padding(vertical = 0.dp, horizontal = 0.dp)) {
            Text(label)
            WidthLabel(availableWidth.toInt())
            Box(Modifier.width((availableWidth / 2).dp).height(20.dp).testTag("halfWidth"))
            if (availableWidth > 200) Text("Wide") else Text("Narrow")
        }
    }
}

@Composable
fun WidthLabel(width: Int) { Text("Width " + width) }

@Composable
fun Propagate() {
    BoxWithConstraints(Modifier.size(100.dp), propagateMinConstraints = true) { Text("Fill") }
}
