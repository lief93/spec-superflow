package degradation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable fun PrivateModifier(enabled: Boolean = true) {
    val scrolling = if (enabled) Modifier.verticalScroll(rememberScrollState()) else Modifier
    Text("Before")
    BoxWithConstraints(scrolling) { Text("Omitted constraints") }
    Text("After")
}

@Composable fun SharedModifier() {
    val scrolling = Modifier.verticalScroll(rememberScrollState())
    BoxWithConstraints(scrolling) { Text("Omitted constraints") }
    Box(scrolling) { Text("Required") }
}
