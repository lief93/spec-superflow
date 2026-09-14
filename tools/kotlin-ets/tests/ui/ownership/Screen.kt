package ownership

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember

@Composable
fun OwnershipPage(seed: Int = 3) {
    val count = remember { mutableStateOf(0) }
    Column {
        Chain("heading")
        Action("increment") { count.value = count.value + 1 }
        Action("captured") { makeAction(Counter(), seed)() }
        Frame { Text("count:" + count.value) }
        DeepDependent("captured")
    }
}
