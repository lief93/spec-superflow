package clipping

import androidx.compose.runtime.Composable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.CutCornerShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable fun Tile(shape: Shape) {
    Box(Modifier.size(80.dp).clip(shape).background(Color.Red).testTag("circle"))
}
@Composable fun DefaultTile(shape: Shape = RoundedCornerShape(6.dp)) {
    Box(Modifier.size(80.dp).clip(shape).background(Color.Red).testTag("default"))
}
@Composable fun Page() {
    Column {
        Tile(CircleShape)
        DefaultTile()
        Box(Modifier.size(160.dp, 80.dp).clip(CircleShape).background(Color.Blue).testTag("capsule"))
        Box(Modifier.size(80.dp).background(Color.Green).clip(CircleShape).testTag("outside"))
        Box(Modifier.size(80.dp).padding(10.dp).clip(CircleShape).background(Color.Red).testTag("padded"))
        Tile(RectangleShape)
    }
}
@Composable fun UnsupportedShape() { Box(Modifier.size(20.dp).clip(RoundedCornerShape(topStart = 4.dp, topEnd = 8.dp))) }
@Composable fun CutThroughHelper() { Tile(CutCornerShape(4.dp)) }
