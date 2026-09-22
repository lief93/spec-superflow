package shapes

import androidx.compose.foundation.shape.CutCornerShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp

val ProjectShapes = Shapes(
    small = RoundedCornerShape(6.dp),
    medium = RoundedCornerShape(
        topStart = 4.dp,
        topEnd = 8.dp,
        bottomEnd = 12.dp,
        bottomStart = 16.dp,
    ),
    large = CutCornerShape(
        topStart = 4.dp,
        topEnd = 8.dp,
        bottomEnd = 12.dp,
        bottomStart = 16.dp,
    ),
)

@Composable
fun ProjectTheme(content: @Composable () -> Unit) {
    MaterialTheme(shapes = ProjectShapes, content = content)
}
