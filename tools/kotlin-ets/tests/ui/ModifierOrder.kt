package order

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun ModifierOrder() {
    val hits = remember { mutableStateOf(0) }
    Column {
        Row {
            repeat(1) {
                Box(
                    Modifier.testTag("outer-hit").clickable { hits.value = hits.value + 1 }
                        .padding(4.dp).width(20.dp).height(8.dp).background(Color.Black)
                )
            }
        }
        Spacer(Modifier.height(48.dp))
        Row {
            repeat(1) {
                Box(
                    Modifier.padding(4.dp).testTag("inner-hit").clickable { hits.value = hits.value + 1 }
                        .width(20.dp).height(8.dp).background(Color.Black)
                )
            }
        }
        Spacer(Modifier.height(48.dp))
        Text("Hits " + hits.value)
    }
}
