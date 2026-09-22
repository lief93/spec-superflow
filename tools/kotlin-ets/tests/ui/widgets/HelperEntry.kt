package widgethelpers

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun HelperEntry(title: String, label: String, onAction: () -> Unit) {
    ActionCard(title = title, onAction = onAction) {
        Text(label)
    }
}
