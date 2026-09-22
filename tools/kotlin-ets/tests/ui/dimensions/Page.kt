package dimensions

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.*

fun width(value: Double): Dp = value.dp
fun fontSize(value: Int): TextUnit = value.sp
fun dpValue(value: Dp): Float = value.value
fun spValue(value: TextUnit): Float = value.value
fun choose(wide: Boolean): Dp = if (wide) 96.dp else 48.dp

@Composable fun Content(width: Dp, fontSize: TextUnit) {
    Column(Modifier.width(width).height(64.dp).testTag("dimensions")) {
        Text("Dimensions", fontSize = fontSize)
    }
}
@Composable fun Page() {
    val width = choose(true)
    val size = fontSize(18)
    Content(width, size)
}

@Composable fun Em() { Text("unsupported", fontSize = 2.em) }
@Composable fun Unspecified() { Box(Modifier.width(Dp.Unspecified)) }
@Composable fun Zero() { Box(Modifier.width(0.dp)) }
@Composable fun Constraints() {
    Box(Modifier.sizeIn(minWidth = Dp.Unspecified, maxWidth = Dp.Unspecified))
}
