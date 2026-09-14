package typedexpressions

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun TypedExpressions(ratio: Float = 0.5f, active: Boolean = true) {
    Box(Modifier.fillMaxWidth(ratio).height(8.dp)
        .background(if (active) Color.Red else Color.Black)
        .testTag("typed \"value\""))
}
