package providetextstyle

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

@Composable
fun Relay(content: @Composable () -> Unit) {
    Surface { content() }
}

@Composable
fun SharedLabel() {
    Text("Shared")
}

@Composable
fun Page() {
    MaterialTheme(typography = Typography(bodyLarge = TextStyle(
        color = Color.Blue,
        fontSize = 18.sp,
        fontWeight = FontWeight.Normal,
        letterSpacing = 0.5.sp,
        lineHeight = 24.sp,
    ))) {
        Column {
            Text("Theme body")
            ProvideTextStyle(TextStyle(lineHeight = 32.sp, letterSpacing = 1.sp)) {
                Text("Outer provider")
                ProvideTextStyle(TextStyle(fontSize = 22.sp)) {
                    Text("Nested provider")
                    Text("Explicit style", style = TextStyle(
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 2.sp,
                    ))
                    Text("Explicit field", fontSize = 30.sp, style = TextStyle(lineHeight = 35.sp))
                    Relay { Text("Relayed") }
                    SharedLabel()
                }
            }
            Button(onClick = {}) { SharedLabel() }
            Text("Restored")
        }
    }
}
