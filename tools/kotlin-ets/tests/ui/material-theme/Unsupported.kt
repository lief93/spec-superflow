package materialtheme

import androidx.compose.runtime.Composable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.Text
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Switch
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.VerticalDivider
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.contentColorFor
import androidx.compose.ui.graphics.Color

@Composable fun Styled() { MaterialTheme(typography = Typography()) { Text("Custom style") } }
@Composable fun colorValue(): Color = MaterialTheme.colorScheme.primary
@Composable fun ValueHelper() { Text("Helper", color = colorValue()) }
@Composable fun ThemedButton() { MaterialTheme { Button(onClick = {}) { Text("Button") } } }
@Composable fun ThemedCheckbox() { MaterialTheme { Checkbox(checked = false, onCheckedChange = {}) } }
@Composable fun ThemedSwitch() { MaterialTheme { Switch(checked = false, onCheckedChange = {}) } }
@Composable fun ThemedDivider() { MaterialTheme { HorizontalDivider() } }
@Composable fun ThemedVerticalDivider() { MaterialTheme { VerticalDivider() } }
@Composable fun ExplicitSchemeLookup() {
    MaterialTheme(colorScheme = lightColorScheme(primary = Color.Red)) {
        val other = lightColorScheme(primary = Color.Blue, onPrimary = Color.Yellow)
        Text("Other", color = other.contentColorFor(Color.Blue))
    }
}
