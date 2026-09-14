package touch

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
fun TouchTargets() {
    val selected = remember { mutableStateOf(-1) }
    Column {
        Row(Modifier.padding(6.dp)) {
            repeat(3) { choice ->
                Box(Modifier.padding(3.dp).width(22.dp).height(10.dp).background(Color.Black)
                    .clickable { selected.value = choice })
            }
        }
        Text("Selected " + selected.value)
    }
}
