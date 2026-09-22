package widgetscroll

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun NegativeScrollInitial() {
    val state = rememberScrollState(initial = -1)
    Column(Modifier.verticalScroll(state)) { Text("Negative") }
}

@Composable
fun DynamicScrollInitial(initial: Int = 1) {
    val state = rememberScrollState(initial = initial)
    Column(Modifier.verticalScroll(state)) { Text("Dynamic") }
}

@Composable
fun ReverseScroll() {
    val state = rememberScrollState()
    Column(Modifier.verticalScroll(state, reverseScrolling = false)) { Text("Reverse") }
}

@Composable
fun FlingScroll() {
    val state = rememberScrollState()
    Column(Modifier.verticalScroll(state, flingBehavior = null)) { Text("Fling") }
}

@Composable
fun Overscroll() {
    val state = rememberScrollState()
    Column(Modifier.verticalScroll(state, overscrollEffect = null)) { Text("Overscroll") }
}

@Composable
fun InlineScrollState() {
    Column(Modifier.verticalScroll(rememberScrollState())) { Text("Inline") }
}

private fun launchScroll(block: suspend () -> Unit) = Unit

@Composable
fun ProgrammaticScroll() {
    val state = rememberScrollState()
    Button(onClick = { launchScroll { state.animateScrollTo(10) } }) {
        Text("Programmatic")
    }
}
