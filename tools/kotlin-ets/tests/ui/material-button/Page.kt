package materialbutton

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

val Accent = Color(0xFF336699)

@Composable fun Action(modifier: Modifier, colors: ButtonColors, enabled: Boolean, clicked: () -> Unit) {
    Button(onClick = clicked, modifier = modifier, colors = colors, enabled = enabled,
        shape = RoundedCornerShape(12.dp), contentPadding = PaddingValues(16.dp),
        border = BorderStroke(1.dp, Color.Green)) {
        Text("Action")
    }
}

@Composable fun Page() {
    val count = remember { mutableStateOf(0) }
    val colors = ButtonDefaults.buttonColors(containerColor = Color.Red, contentColor = Color.White,
        disabledContainerColor = Color.Blue, disabledContentColor = Color.Yellow)
    Column(Modifier.width(240.dp)) {
        Action(Modifier.fillMaxWidth().testTag("active"), colors, true) { count.value = count.value + 1 }
        Action(Modifier.fillMaxWidth().testTag("disabled"), colors, false) { count.value = count.value + 100 }
        TextButton(onClick = { count.value = count.value + 1 }, modifier = Modifier.testTag("text-button"),
            colors = ButtonDefaults.textButtonColors(contentColor = Accent)) { Text("Retry") }
        Text("Count: ${count.value}", modifier = Modifier.testTag("count"))
    }
}

@Composable fun UnsupportedInteraction() {
    Button(onClick = {}, interactionSource = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }) { Text("no") }
}

var receiverCalls = 0
fun defaults(): ButtonDefaults {
    receiverCalls += 1
    return ButtonDefaults
}
@Composable fun UnsupportedReceiver() {
    val colors = defaults().buttonColors()
    Button(onClick = {}, colors = colors) { Text("receiver") }
}
@Composable fun UnsupportedTextReceiver() {
    val colors = defaults().textButtonColors()
    TextButton(onClick = {}, colors = colors) { Text("receiver") }
}
