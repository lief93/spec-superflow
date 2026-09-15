package surface

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
fun Page() {
    Column {
        Surface(modifier = Modifier.width(80.dp).height(40.dp), color = Color.Black, contentColor = Color.White) {
            Text("Inherited")
        }
        Surface(Modifier.width(80.dp).height(40.dp), color = Color.Black, contentColor = Color.White) {
            Text("Override", color = Color.Red)
        }
        Surface(Modifier.width(80.dp).height(40.dp), color = Color.Yellow, contentColor = Color.White) {
            BasicText("Basic")
        }
        Text("Outside", color = Color.Black)
    }
}
