package shapes.values

import androidx.compose.foundation.shape.CutCornerShape
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.dp

fun uniformCut(): Shape = CutCornerShape(5.dp)
fun individualCut(): Shape = CutCornerShape(
    topStart = 1.dp,
    topEnd = 2.dp,
    bottomEnd = 3.dp,
    bottomStart = 4.dp,
)
