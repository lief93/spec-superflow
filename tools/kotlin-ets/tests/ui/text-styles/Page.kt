package fontfixtures

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.dp

@Composable fun Page() {
    val style = heading(18.sp, family())
    Column(Modifier.width(280.dp)) {
        Text("Custom style", style = style)
        Text("Explicit overrides", color = Color.Red, fontSize = 22.sp, fontWeight = FontWeight.Normal, style = style)
    }
}
