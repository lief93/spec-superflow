package shapes.unsupported

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Outline
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp

private val Round = Shapes(medium = RoundedCornerShape(8.dp))
private val Sharp = Shapes(medium = RoundedCornerShape(20.dp))

@Composable
fun RuntimeTheme(round: Boolean, content: @Composable () -> Unit) {
    MaterialTheme(shapes = if (round) Round else Sharp, content = content)
}

@Composable fun RuntimePage() = Box(Modifier.clip(MaterialTheme.shapes.medium))
@Composable fun PercentagePage() = Box(Modifier.clip(RoundedCornerShape(50)))

private object CustomShape : Shape {
    override fun createOutline(size: Size, layoutDirection: LayoutDirection, density: Density): Outline =
        Outline.Rectangle(Rect(0f, 0f, size.width, size.height))
}

@Composable fun CustomPage() = Box(Modifier.clip(CustomShape))
