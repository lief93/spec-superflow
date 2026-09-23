package implicitcontext

import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider

@Composable
private fun ContextButton(label: String) {
    TextButton(onClick = {}) {
        ProvideTextStyle(MaterialTheme.typography.labelSmall) {
            ContextLabel(label)
        }
    }
}

@Composable
fun Page() {
    MaterialTheme {
        CompositionLocalProvider(
            LocalName provides evaluatedName("theme-first"),
            LocalCount provides evaluatedCount(1),
        ) {
            CrossFileRelay("outer") { ContextButton("theme-first") }
            CompositionLocalProvider(
                LocalCount provides evaluatedCount(2),
                LocalName provides evaluatedName("shadowed"),
            ) {
                BoxWithConstraints { ContextButton("shadowed") }
            }
            ContextButton("restored")
        }
    }
    CompositionLocalProvider(
        LocalCount provides evaluatedCount(3),
        LocalName provides evaluatedName("local-first"),
    ) {
        MaterialTheme {
            CrossFileRelay("inner") { ContextButton("local-first") }
        }
    }
}
