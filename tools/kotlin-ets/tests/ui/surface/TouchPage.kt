package surface

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable fun TouchPage() {
    val below = remember { mutableStateOf(0) }
    val inside = remember { mutableStateOf(0) }
    Column {
        Box {
            Button(onClick = { below.value = below.value + 1 }, modifier = Modifier.width(160.dp).height(100.dp)) {
                Text("Behind")
            }
            Surface(modifier = Modifier.width(160.dp).height(100.dp), color = Color.Black, contentColor = Color.White) {
                Column {
                    Button(onClick = { inside.value = inside.value + 1 }) { Text("Inside") }
                }
            }
        }
        Text("Inside " + inside.value, color = Color.Black)
        Text("Behind " + below.value, color = Color.Black)
    }
}
