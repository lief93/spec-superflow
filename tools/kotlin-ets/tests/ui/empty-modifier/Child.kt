package emptymodifier
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun Child(modifier: Modifier = Modifier) {
    Box(modifier.padding(16.dp))
}

var reads = 0
fun same(modifier: Modifier): Modifier {
    reads++
    return modifier
}
fun identity(): Boolean = same(Modifier) === same(Modifier)
