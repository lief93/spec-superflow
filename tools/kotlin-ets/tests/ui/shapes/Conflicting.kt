package shapes.conflicting

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp

private val First = Shapes(medium = RoundedCornerShape(8.dp))
private val Second = Shapes(medium = RoundedCornerShape(20.dp))

@Composable fun FirstTheme(content: @Composable () -> Unit) = MaterialTheme(shapes = First, content = content)
@Composable fun SecondTheme(content: @Composable () -> Unit) = MaterialTheme(shapes = Second, content = content)
@Composable fun Page() = Box(Modifier.clip(MaterialTheme.shapes.medium))
