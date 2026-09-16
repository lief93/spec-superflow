package degradation

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

fun visible(): Boolean = true

@Composable fun UnsupportedType() {
    Text("Before")
    AnimatedVisibility(enter = fadeIn(), visible = visible()) {
        Text("Skipped")
    }
    Text("After")
}

@Composable fun ExplicitUnsupportedType() {
    val enter = fadeIn()
    AnimatedVisibility(enter = enter, visible = visible()) { Text("Skipped") }
}
