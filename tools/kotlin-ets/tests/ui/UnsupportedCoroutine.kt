package negative

import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private var clicked = false

fun singleClick(delayMillis: Long = 300, onClick: () -> Unit): () -> Unit = {
    if (!clicked) {
        clicked = true
        onClick()
        CoroutineScope(Dispatchers.Main).launch {
            delay(delayMillis)
            clicked = false
        }
    }
}

@Composable
fun TimerButton(onClick: () -> Unit) {
    Button(onClick = onClick) { Text("Timer callback") }
}

@Composable
fun TimerPage() {
    TimerButton(onClick = singleClick { clicked = false })
}

@Composable
fun UnknownPage() {
    val scope = rememberCoroutineScope()
    Button(onClick = { scope.launch { delay(1) } }) { Text("Unsupported coroutine") }
}
