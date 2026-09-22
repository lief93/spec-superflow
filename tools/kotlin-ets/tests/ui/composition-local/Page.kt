package compositionlocal

import androidx.compose.material3.Text
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.staticCompositionLocalOf

data class Accent(val label: String)

private val LocalCount = compositionLocalOf { -1 }
private val LocalName = staticCompositionLocalOf { "default" }
private val LocalAccent = compositionLocalOf { Accent("none") }

private var evaluationTrace = ""

private fun counted(value: Int): Int {
    evaluationTrace += "count;"
    return value
}

private fun named(value: String): String {
    evaluationTrace += "name;"
    return value
}

private fun accented(value: String): Accent {
    evaluationTrace += "accent;"
    return Accent(value)
}

@Composable
fun Relay(content: @Composable () -> Unit) {
    content()
}

@Composable
fun Reading(label: String) {
    Text("$label:${LocalCount.current}:${LocalName.current}:${LocalAccent.current.label}")
}

@Composable
fun Page() {
    Reading("default")
    CompositionLocalProvider(
        LocalCount provides counted(1),
        LocalName provides named("outer"),
        LocalAccent provides accented("blue"),
    ) {
        Reading("outer")
        Relay { Reading("relayed") }
        MaterialTheme { Relay { Reading("material-relayed") } }
        CompositionLocalProvider(LocalCount provides counted(2)) {
            Reading("nested")
        }
        Reading("restored-outer")
    }
    Reading("restored-default")
    Text(evaluationTrace)
}
