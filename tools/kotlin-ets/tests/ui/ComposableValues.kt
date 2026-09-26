package composablevalues

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun getRawString(key: String): String = if (key == "title") "Field Notes" else "Unknown " + key

@Composable
fun ComposableRow(content: @Composable RowScope.() -> Unit) {
    Row(content = content)
}

@Composable
fun ComposableValues() {
    Column {
        Text(getRawString("title"))
        Text(getRawString("other"))
        ComposableRow { Text("Scoped content", Modifier.weight(1f)) }
        Row { Text("Direct scoped content", Modifier.weight(1f)) }
    }
}
