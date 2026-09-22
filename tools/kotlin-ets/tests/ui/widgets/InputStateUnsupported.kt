package widgetstateinput

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun UnsupportedInputStateBranch(state: UiState) {
    if (state.loading) {
        while (false) { }
    } else {
        Text(state.content)
    }
}
