package uiinit

import androidx.compose.runtime.Composable
import androidx.compose.foundation.text.BasicText

val third = mark(3)
@Composable fun Other(value: Int = mark(4)) {
    BasicText("Other: $value")
}
