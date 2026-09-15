package materialtheme

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.contentColorFor
import androidx.compose.ui.graphics.Color

@Composable
fun Forward(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = lightColorScheme(primary = Color.Blue, onPrimary = Color.Yellow)) {
        Surface(color = MaterialTheme.colorScheme.primary) { content() }
    }
}

@Composable
fun Page() {
    MaterialTheme(colorScheme = lightColorScheme(primary = Color.Red, onPrimary = Color.Green)) {
        Column {
            Surface(color = MaterialTheme.colorScheme.primary) { Text("Outer") }
            Forward { Text("Forwarded"); Text("Explicit", color = MaterialTheme.colorScheme.primary) }
            Surface(color = MaterialTheme.colorScheme.primary) { Text("Restored") }
            Surface(color = Color.Magenta, contentColor = Color.Cyan) {
                Surface(color = Color(0xFF010203)) { Text("Fallback") }
            }
            MaterialTheme { Surface(color = MaterialTheme.colorScheme.primary) { Text("Inherited") } }
            Text("Direct", color = contentColorFor(MaterialTheme.colorScheme.primary))
        }
    }
}
