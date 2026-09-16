package uiinit

import androidx.compose.runtime.Composable
import androidx.compose.foundation.text.BasicText

fun fail(): Int {
    mark(5)
    throw IllegalStateException("initialization failed")
}
val failed = fail()
@Composable fun Failure() { BasicText("Must not render") }
