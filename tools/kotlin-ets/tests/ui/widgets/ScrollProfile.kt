package widgetscroll

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun ScrollProfile() {
    val vertical = rememberScrollState(initial = 12)
    val horizontal = rememberScrollState(initial = 7)
    Column {
        Column(Modifier.fillMaxHeight().verticalScroll(vertical).fillMaxWidth()) {
            Text("Vertical ${vertical.value}")
            Text("Last")
        }
        Row(Modifier.fillMaxWidth().horizontalScroll(horizontal, enabled = false).fillMaxHeight()) {
            Text("Horizontal ${horizontal.value}")
            Text("Right")
        }
    }
}
