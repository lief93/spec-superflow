package negative

import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun UnknownPage() {
    val scope = rememberCoroutineScope()
    Button(onClick = { scope.launch { delay(1) } }) { Text("Unsupported coroutine") }
}
