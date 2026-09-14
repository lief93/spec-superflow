package basiccontrols

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Switch
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun BasicControls(enabled: Boolean = true, line: Int = 2) {
    val selected = remember { mutableStateOf(false) }
    Column {
        BasicText(if (selected.value) "Selected" else "Not selected", maxLines = 2)
        HorizontalDivider(thickness = line.dp, color = Color.Red, modifier = Modifier.testTag("horizontal"))
        VerticalDivider(thickness = 3.dp, color = Color.Black, modifier = Modifier.height(24.dp))
        Checkbox(checked = selected.value, onCheckedChange = { next -> selected.value = next }, enabled = enabled)
        Switch(checked = selected.value, onCheckedChange = { selected.value = it }, enabled = enabled)
    }
}
