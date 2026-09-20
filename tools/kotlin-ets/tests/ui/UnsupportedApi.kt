package negative

import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun UnknownPage() {
    Text("Must not survive an incomplete translation")
    LazyRow { item { Text("Unsupported lazy layout") } }
}
