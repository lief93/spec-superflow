package widgethelpers

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun ActionCard(
    title: String,
    enabled: Boolean = true,
    onAction: () -> Unit,
    content: @Composable () -> Unit,
) {
    Column {
        Text(title)
        Button(onClick = onAction, enabled = enabled) {
            content()
        }
    }
}
