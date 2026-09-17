package pointerinput

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp

@Composable
fun Page() {
    val behind = remember { mutableStateOf(0) }
    val inside = remember { mutableStateOf(0) }
    Column {
        Text("Behind ${behind.value}")
        Text("Inside ${inside.value}")
        Box(Modifier.size(200.dp)) {
            Button(onClick = { behind.value = behind.value + 1 }, modifier = Modifier.fillMaxSize()) { Text("Behind button") }
            Box(Modifier.fillMaxSize().pointerInput(Unit) {}) {
                Button(onClick = { inside.value = inside.value + 1 }) { Text("Inside button") }
            }
        }
    }
}

@Composable
fun Nonempty() {
    Box(Modifier.pointerInput(Unit) { awaitPointerEventScope { awaitPointerEvent() } })
}

private fun key(): Int = 1

@Composable
fun EvaluatedKey() {
    Box(Modifier.pointerInput(key()) {})
}
