package uiinit

import androidx.compose.runtime.Composable
import androidx.compose.foundation.text.BasicText

val first = mark(1)
val second = mark(2)

@Composable fun Page() {
    BasicText("Ready")
    if (showOther) Other()
    if (showFailure) Failure()
}
