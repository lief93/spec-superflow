package colorvalues

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

@Composable
fun Label(value: Color = Color.Unspecified) {
    Text("Typed color", color = value)
}

@Composable
fun Page() {
    Column(Modifier.background(selectColor(1, Color.White, Color.Black))) {
        Text("Inherited color", color = Color.Unspecified)
        Label()
        Label(Color.Unspecified)
        Label(selectColor(0, Palette(Color.Red).foreground, Color.Black))
    }
}

@Composable
fun UnsupportedBackground() {
    Column(Modifier.background(Color.Unspecified)) {}
}
