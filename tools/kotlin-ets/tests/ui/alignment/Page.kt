package alignment

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

fun horizontal(center: Boolean): Alignment.Horizontal = if (center) Alignment.CenterHorizontally else Alignment.End
fun vertical(center: Boolean): Alignment.Vertical = if (center) Alignment.CenterVertically else Alignment.Bottom
fun corner(end: Boolean): Alignment = if (end) Alignment.BottomEnd else Alignment.TopStart

@Composable
fun Sample(name: String, alignment: Alignment) {
    Box(Modifier.size(100.dp, 60.dp).testTag(name), contentAlignment = alignment) {
        Box(Modifier.size(20.dp, 10.dp).testTag(name + "-child"))
    }
}

@Composable
fun Page() {
    Column {
        Column(Modifier.size(100.dp, 60.dp).testTag("column"), horizontalAlignment = horizontal(true)) {
            Box(Modifier.size(20.dp, 10.dp).testTag("column-child"))
        }
        Row(Modifier.size(100.dp, 60.dp).testTag("row"), verticalAlignment = vertical(true)) {
            Box(Modifier.size(20.dp, 10.dp).testTag("row-child"))
        }
        Sample("top-start", corner(false))
        Sample("top-center", Alignment.TopCenter)
        Sample("top-end", Alignment.TopEnd)
        Sample("center-start", Alignment.CenterStart)
        Sample("center", Alignment.Center)
        Sample("center-end", Alignment.CenterEnd)
        Sample("bottom-start", Alignment.BottomStart)
        Sample("bottom-center", Alignment.BottomCenter)
        Sample("bottom-end", corner(true))
    }
}
