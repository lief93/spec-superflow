package modifiernamed

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Composable fun Dot(circleSize: Dp, circleColor: Color) {
    Box(Modifier.size(circleSize).background(shape = CircleShape, color = circleColor).testTag("dot"))
}

@Composable fun Page() {
    Column { Dot(24.dp, Color.Red) }
}

var calls = 0
fun nextColor(): Color { calls += 1; return Color.Red }

@Composable fun Effectful() {
    Box(Modifier.size(24.dp).background(shape = CircleShape, color = nextColor()))
}
