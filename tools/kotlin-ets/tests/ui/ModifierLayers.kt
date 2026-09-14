package layers

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun ModifierLayers() {
    Column {
        Box(Modifier.width(20.dp).height(8.dp).background(Color.Black).testTag("direct"))
        Box(Modifier.padding(4.dp).width(20.dp).height(8.dp).background(Color.Red).testTag("outside"))
        Box(Modifier.width(28.dp).height(16.dp).padding(4.dp).background(Color.Gray).testTag("inside"))
        Box(Modifier.background(Color.Black).padding(4.dp).width(20.dp).height(8.dp)
            .background(Color.Red).testTag("paint"))
        Box(Modifier.width(20.dp).width(40.dp).height(8.dp).background(Color.Black).testTag("fixed"))
        Box(Modifier.width(20.dp).height(8.dp).background(Color.Black)
            .background(Color.Transparent).testTag("alpha"))
    }
}
