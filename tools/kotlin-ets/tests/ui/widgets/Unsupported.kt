package widgetsnegative

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable fun UnknownWidget() { Checkbox(checked = true, onCheckedChange = {}) }
@Composable fun UnknownModifier() { Text("x", Modifier.fillMaxWidth()) }
@Composable fun UnknownArgument() { Text("x", fontSize = 20.sp) }
@Composable fun Conditional() { if (true) Text("x") else Text("y") }
@Composable fun Helper() { LocalText("x") }
@Composable fun LocalText(value: String) { Text(value) }
fun effect(): String = "effect"
@Composable fun EffectfulValue() { Text(effect()) }
fun callbackFactory(): () -> Unit = {}
@Composable fun CallbackFactory() { Button(onClick = callbackFactory()) { Text("x") } }
@Composable fun NegativePadding() { Text("x", Modifier.padding((-1).dp)) }
@Composable fun MutableLocal() { var value = "x"; Text(value) }
@Composable fun EarlyReturn() { Text("before"); return; Text("unreachable") }
