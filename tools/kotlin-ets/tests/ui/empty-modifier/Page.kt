package emptymodifier
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun Page() {
    Column {
        Child()
        Child(same(Modifier))
    }
}
@Composable
fun Nonempty() {
    Child(Modifier.padding(8.dp))
}

@Composable
fun DefaultFailure() { BadDefault() }
