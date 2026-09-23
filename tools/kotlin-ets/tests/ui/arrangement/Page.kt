package arrangement

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

fun spacing(base: Int, extra: Int): Arrangement.HorizontalOrVertical = Arrangement.spacedBy((base + extra).dp)

@Composable fun Horizontal(arrangement: Arrangement.Horizontal) {
    Row(horizontalArrangement = arrangement, modifier = Modifier.testTag("row")) {
        Box(Modifier.size(24.dp).background(Color.Red).testTag("r1"))
        Box(Modifier.size(24.dp).background(Color.Red).testTag("r2"))
        Box(Modifier.size(24.dp).background(Color.Red).testTag("r3"))
    }
}

@Composable fun Vertical(arrangement: Arrangement.Vertical) {
    Column(verticalArrangement = arrangement, modifier = Modifier.testTag("column")) {
        Box(Modifier.size(20.dp).background(Color.Blue).testTag("c1"))
        Box(Modifier.size(20.dp).background(Color.Blue).testTag("c2"))
    }
}

@Composable fun Page() {
    Column {
        Text("Spacing before")
        Column(verticalArrangement = Arrangement.Center) { Text("Centered") }
        Horizontal(spacing(6, 2))
        Vertical(Arrangement.spacedBy(12.dp))
        Text("Spacing after")
    }
}

@Composable fun UnsupportedAlignment() {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally)) { Text("Aligned") }
}
