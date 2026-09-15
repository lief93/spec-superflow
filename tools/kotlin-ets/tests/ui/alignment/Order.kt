package alignment

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

var phase = 0
fun nextWidth(): Int { phase = 1; return 100 }
fun afterWidth(): Alignment.Horizontal = if (phase == 0) Alignment.Start else Alignment.End
fun afterWidthVertical(): Alignment.Vertical = if (phase == 0) Alignment.Top else Alignment.Bottom
fun afterWidthBox(): Alignment = if (phase == 0) Alignment.TopStart else Alignment.BottomEnd

@Composable fun ColumnOrder() {
    Column(modifier = Modifier.width(nextWidth().dp), horizontalAlignment = afterWidth()) {}
}
@Composable fun RowOrder() {
    Row(modifier = Modifier.width(nextWidth().dp), verticalAlignment = afterWidthVertical()) {}
}
@Composable fun BoxOrder() {
    Box(modifier = Modifier.width(nextWidth().dp), contentAlignment = afterWidthBox()) {}
}

@Composable fun BoundOrder() {
    val width = nextWidth()
    val alignment = afterWidth()
    Column(modifier = Modifier.width(width.dp), horizontalAlignment = alignment) {}
}
