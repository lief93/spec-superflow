package typography

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

@Composable fun Label() { Text("Inherited") }
@Composable fun Page() {
    MaterialTheme(typography = Typography(bodyLarge = TextStyle(fontSize = 27.sp),
        labelLarge = TextStyle(fontSize = 21.sp), titleSmall = TextStyle(fontSize = 23.sp))) {
        Column {
            val theme = MaterialTheme
            Surface { Label() }
            Button(onClick = {}) { Text("Button") }
            Text("Explicit", style = MaterialTheme.typography.titleSmall, fontSize = 19.sp)
            Text("Copied", style = MaterialTheme.typography.titleLarge.copy(
                fontSize = 30.sp, color = MaterialTheme.colorScheme.onBackground))
            MaterialTheme(typography = Typography(bodyLarge = TextStyle(fontSize = 31.sp))) {
                Text("Nested", style = theme.typography.bodyLarge, color = theme.colorScheme.primary)
            }
        }
    }
}
