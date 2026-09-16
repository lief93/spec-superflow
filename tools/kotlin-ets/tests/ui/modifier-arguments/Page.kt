package modifierarguments

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Composable fun Card(modifier: Modifier, text: String) {
    Box(modifier.then(Modifier.height(24.dp))) { Text(text) }
}
@Composable fun Forward(modifier: Modifier, text: String) { Card(modifier, text) }
@Composable fun Page() {
    Column(Modifier.width(200.dp)) {
        Forward(Modifier.fillMaxWidth(), "first")
        Forward(Modifier.fillMaxWidth(), "second")
        Card(Modifier.width(80.dp), "narrow")
        Card(Modifier, "plain")
        Card(Modifier.padding(horizontal = 8.dp), "horizontal")
        Card(Modifier.padding(vertical = 8.dp), "vertical")
        Card(Modifier.padding(8.dp), "all")
        Card(Modifier.padding(horizontal = 8.dp), "horizontal-again")
    }
}
@Composable fun Dynamic(width: Dp = 12.dp) { Card(Modifier.width(width), "dynamic") }
var calls = 0
fun nextWidth(): Dp { calls += 1; return 30.dp }
@Composable fun Effectful() { Card(Modifier.width(nextWidth()), "effectful") }
@Composable fun DefaultFailure() { BadDefault(Modifier.width(80.dp)) }
