package scroll

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun Page() {
    Column {
        Scrolling(true)
        Scrolling(false)
        Row(Modifier.size(120.dp).horizontalScroll(rememberScrollState()).testTag("horizontalContent")) {
            Text("Left", Modifier.width(160.dp))
            Text("Right", Modifier.width(160.dp))
        }
    }
}

@Composable
fun Scrolling(enabled: Boolean) {
    val scrollModifier = if (enabled) { Modifier.verticalScroll(rememberScrollState()) } else { Modifier }
    Column(Modifier.size(120.dp).then(scrollModifier).padding(8.dp).testTag("verticalContent")) {
        Text("First", Modifier.height(100.dp))
        Text("Last", Modifier.height(100.dp))
    }
}

@Composable
fun Disabled() {
    Column(Modifier.size(120.dp).verticalScroll(rememberScrollState(), enabled = false)) {
        Text("Long", Modifier.height(400.dp))
    }
}

@Composable
fun Nonzero() {
    Column(Modifier.verticalScroll(rememberScrollState(12))) { Text("Offset") }
}

@Composable
fun Observed() {
    val state = rememberScrollState()
    Column(Modifier.verticalScroll(state)) { Text(state.value.toString()) }
}

@Composable
fun Reverse() {
    Column(Modifier.verticalScroll(rememberScrollState(), reverseScrolling = true)) { Text("Reverse") }
}
