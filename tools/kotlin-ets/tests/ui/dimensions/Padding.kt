package dimensions

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.*

var paddingReads = 0
fun nextPadding(): Dp { paddingReads += 1; return paddingReads.dp }
@Composable fun RepeatedPadding() { Box(Modifier.padding(horizontal = nextPadding())) }
@Composable fun BoundPadding() {
    val padding = nextPadding()
    Box(Modifier.padding(horizontal = padding))
}
