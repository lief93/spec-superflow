package conditionalui

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag

@Composable
fun ConditionalUi(active: Boolean = true) {
    if (active) {
        Box(Modifier.testTag("Active"))
    } else {
        Box(Modifier.testTag("Inactive"))
    }
}
