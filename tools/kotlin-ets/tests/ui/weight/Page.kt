package weightfixtures
import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun Page(first: Float = 1f) {
    Column {
        Column(Modifier.width(120.dp).height(300.dp).testTag("column")) {
            Box(Modifier.height(30.dp).width(80.dp).background(Color.Black).testTag("fixed"))
            Box(Modifier.width(80.dp).weight(first).testTag("weightedOuter").padding(8.dp)
                .background(Color.Red).testTag("weightedInner"))
            Box(Modifier.width(80.dp).weight(2f).background(Color.Blue).testTag("weightedTwo"))
        }
        Row(Modifier.width(300.dp).height(60.dp).testTag("row")) {
            Box(Modifier.width(30.dp).height(40.dp).background(Color.Black).testTag("rowFixed"))
            Box(Modifier.height(40.dp).weight(first).background(Color.Red).testTag("rowOne"))
            Box(Modifier.height(40.dp).weight(2f).background(Color.Blue).testTag("rowTwo"))
        }
    }
}
@Composable
fun NoFill() { Column { Box(Modifier.weight(1f, fill = false)) } }
@Composable
fun Zero() { Column { Box(Modifier.weight(0f)) } }
@Composable
fun Repeated() { Column { Box(Modifier.weight(1f).weight(2f)) } }

@Composable
fun Pass(content: @Composable () -> Unit) { content() }
@Composable
fun UnknownSlotParent() {
    Column(Modifier.height(300.dp)) {
        Pass { Box(Modifier.width(80.dp).weight(1f).padding(8.dp).background(Color.Red)) }
    }
}
