package uiinit

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.foundation.text.BasicText

val initialized = initialize()
fun initialize(): Int {
    mark(1)
    if (showFailure) throw IllegalStateException("failed before remember")
    return 1
}
@Composable fun RememberPage() {
    val state = remember { mutableStateOf(mark(2)) }
    BasicText("${state.value}")
}
