package flowtype

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.emptyFlow

fun identity(values: Flow<String>?): Flow<String>? = values
fun current(values: StateFlow<String>): String = values.value

@Composable
fun Page() {
    val values: Flow<String>? = null
    Text(if (identity(values) == null) "typed" else "live")
}

@Composable
fun Collected() {
    Text(emptyFlow<String>().collectAsState(initial = "seed").value)
}

@Composable
fun Lifecycle() {
    Text(MutableStateFlow("seed").collectAsStateWithLifecycle().value)
}

@Composable
fun Snapshot() {
    Text(current(MutableStateFlow("seed")))
}
