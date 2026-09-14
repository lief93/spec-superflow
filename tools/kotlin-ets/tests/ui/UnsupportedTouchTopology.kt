package negative

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun UnknownPage() {
    Column {
        Box(Modifier.clickable {}.size(20.dp))
        Box(Modifier.clickable {}.size(20.dp))
    }
}
