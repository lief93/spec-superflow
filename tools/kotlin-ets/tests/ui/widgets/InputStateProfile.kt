package widgetstateinput

import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

interface UiState {
    val loading: Boolean
    val error: String?
    val content: String
}

@Composable
fun InputStateProfile(state: UiState, dispatch: (String) -> Unit) {
    when {
        state.loading -> Text("Loading")
        state.error != null -> Button(onClick = { dispatch("retry") }) {
            Text("Error")
        }
        else -> Button(onClick = { dispatch("refresh") }) {
            Text(state.content)
        }
    }
}

@Composable
fun InputStateIfProfile(state: UiState, dispatch: (String) -> Unit) {
    if (state.loading) {
        Text("Loading")
    } else {
        Button(onClick = { dispatch("open") }) { Text(state.content) }
    }
}
