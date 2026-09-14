package negative

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun UnknownPage() {
    Row {
        repeat(2) {
            Box(Modifier.width(20.dp).height(8.dp).clickable(enabled = false) {})
        }
    }
}
