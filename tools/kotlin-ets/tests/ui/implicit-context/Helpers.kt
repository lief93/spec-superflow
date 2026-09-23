package implicitcontext

import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.staticCompositionLocalOf

internal val LocalCount = compositionLocalOf { -1 }
internal val LocalName = staticCompositionLocalOf { "default" }

internal fun evaluatedCount(value: Int): Int = value
internal fun evaluatedName(value: String): String = value

@Composable
internal fun CrossFileFrame(marker: String, content: @Composable () -> Unit) {
    Surface {
        Text(marker)
        content()
    }
}

@Composable
internal fun CrossFileRelay(marker: String, content: @Composable () -> Unit) {
    CrossFileFrame(marker, content)
}

@Composable
internal fun ContextLabel(prefix: String) {
    Text("$prefix:${LocalName.current}:${LocalCount.current}")
}
