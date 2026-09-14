package slotlayouts

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun Pair(prefix: String) {
    Text("one", Modifier.testTag(prefix + "-one").width(40.dp).height(20.dp))
    Text("two", Modifier.testTag(prefix + "-two").width(40.dp).height(20.dp))
}

@Composable
fun VerticalFrame(content: @Composable () -> Unit) {
    Column {
        Text("before", Modifier.testTag("column-before").width(40.dp).height(20.dp))
        content()
        Text("after", Modifier.testTag("column-after").width(40.dp).height(20.dp))
    }
}

@Composable
fun HorizontalFrame(content: @Composable () -> Unit) {
    Row {
        Text("before", Modifier.testTag("row-before").width(40.dp).height(20.dp))
        content()
        Text("after", Modifier.testTag("row-after").width(40.dp).height(20.dp))
    }
}

@Composable
fun SlotLayouts() {
    Column {
        VerticalFrame { Pair("column") }
        HorizontalFrame { Pair("row") }
    }
}
