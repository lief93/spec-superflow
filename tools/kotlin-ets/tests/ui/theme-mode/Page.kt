package thememode

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun Page() {
    if (isSystemInDarkTheme()) Text("Dark") else Text("Light")
}
