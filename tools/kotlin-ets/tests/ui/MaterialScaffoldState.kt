package materialscaffoldstate

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.flow.StateFlow

data class ScreenState(val title: String)

@Composable
fun MaterialScaffoldState(
    state: StateFlow<ScreenState>,
    snackbarHostState: SnackbarHostState = remember { SnackbarHostState() },
    modifier: Modifier = Modifier,
) {
    val uiState by state.collectAsStateWithLifecycle()
    Scaffold(
        modifier = modifier,
        topBar = { Text("Top") },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { paddingValues ->
        val commonModifier = modifier.fillMaxSize().padding(paddingValues)
        Text(uiState.title, modifier = commonModifier)
    }
}
