package wrapcontent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable fun Page() {
    Column {
        Box(Modifier.size(80.dp).testTag("size-outer").wrapContentSize().size(20.dp).background(Color.Red).testTag("size-inner"))
        Box(Modifier.size(80.dp).testTag("height-outer").wrapContentHeight().height(20.dp).background(Color.Blue).testTag("height-inner"))
        Box(Modifier.size(80.dp).testTag("width-outer").wrapContentWidth(Alignment.End).width(20.dp).background(Color.Green).testTag("width-inner"))
        Box(Modifier.wrapContentSize().size(40.dp).testTag("wrap-first"))
    }
}
@Composable fun Unbounded() { Box(Modifier.wrapContentHeight(unbounded = true)) }
fun alignment(): Alignment = Alignment.Center
@Composable fun EffectfulAlignment() { Box(Modifier.wrapContentSize(alignment())) }
