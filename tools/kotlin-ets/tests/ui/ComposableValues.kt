package composablevalues

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun getRawString(key: String): String = if (key == "title") "Field Notes" else "Unknown " + key

@Composable
fun ComposableValues() {
    Column {
        Text(getRawString("title"))
        Text(getRawString("other"))
    }
}
