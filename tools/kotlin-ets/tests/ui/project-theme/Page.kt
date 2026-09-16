package projecttheme

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.ui.platform.LocalContext

fun palette(context: Context, dark: Boolean): ColorScheme =
    if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)

@Composable fun Page() {
    val context = LocalContext.current
    Column {
        MaterialTheme(colorScheme = palette(context, false)) {
            Text("Project light", color = MaterialTheme.colorScheme.primary)
        }
        MaterialTheme(colorScheme = palette(context, true)) {
            Text("Project dark", color = MaterialTheme.colorScheme.primary)
        }
    }
}
