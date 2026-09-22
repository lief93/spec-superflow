package shapes

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp

@Composable
fun ProjectPage() {
    Box(Modifier.size(40.dp).clip(MaterialTheme.shapes.medium))
}

@Composable
fun DefaultPage() {
    Box(Modifier.size(40.dp).clip(MaterialTheme.shapes.extraLarge))
}

@Composable
fun CutPage() {
    Box(Modifier.size(40.dp).clip(MaterialTheme.shapes.large))
}
