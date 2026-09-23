package widgetsnegative

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Text
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.painter.ColorPainter
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage

object UnknownTokens {
    val label: String get() = "unknown"
    val color: Color get() = Color.Red
    val fontSize: TextUnit get() = 20.sp
}

@Composable fun UnknownWidget() { Checkbox(checked = true, onCheckedChange = {}) }
@Composable fun UnknownModifier() { Text("x", Modifier.rotate(15f)) }
@Composable fun WholeTextStyle() { Text("x", style = TextStyle(fontSize = 20.sp)) }
@Composable fun Conditional() { if (true) while (false) { } else Text("y") }
@Composable fun Helper() { LocalText("x") }
@Composable fun LocalText(value: String) { Text(value) }
fun effect(): String = "effect"
@Composable fun EffectfulValue() { Text(effect()) }
fun callbackFactory(): () -> Unit = {}
@Composable fun CallbackFactory() { Button(onClick = callbackFactory()) { Text("x") } }
@Composable fun NegativePadding() { Text("x", Modifier.padding((-1).dp)) }
@Composable fun MutableLocal() { var value = "x"; Text(value) }
@Composable fun EarlyReturn() { Text("before"); return; Text("unreachable") }
@Composable fun ArbitraryPainter() { Image(ColorPainter(Color.Red), null) }
@Composable fun RichText() { Text(AnnotatedString("rich")) }
@Composable fun NonUrlImageModel() { AsyncImage(7, null) }
@Composable fun BadImageUrl() { AsyncImage("file:///private/image.png", null) }
@Composable fun RichTextField() { BasicTextField(TextFieldValue("rich"), {}) }
@Composable fun DecorationTextField() {
    BasicTextField("value", {}, decorationBox = { inner -> inner() })
}
@Composable fun MaterialDecoration() {
    androidx.compose.material3.TextField("value", {}, label = { Text("label") })
}
fun inputCallbackFactory(): (String) -> Unit = {}
@Composable fun TextFieldCallbackFactory() {
    BasicTextField("value", inputCallbackFactory())
}
@Composable fun BrushBackground() {
    Text("x", Modifier.background(Brush.horizontalGradient(listOf(Color.Red, Color.Blue))))
}
@Composable fun BrushBorder() {
    Text("x", Modifier.border(1.dp, Brush.horizontalGradient(listOf(Color.Red, Color.Blue)), CircleShape))
}
@Composable fun AnimatedModifier() { Text("x", Modifier.animateContentSize()) }
@Composable fun NonUniformShape() {
    Text("x", Modifier.clip(RoundedCornerShape(topStart = 2.dp, topEnd = 4.dp)))
}
@Composable fun OffsetLambda() { Text("x", Modifier.offset { IntOffset.Zero }) }
@Composable fun ClickSemantics() {
    Text("x", Modifier.clickable(onClickLabel = "action", role = Role.Button) {})
}
@Composable fun ClickFactory() { Text("x", Modifier.clickable(onClick = callbackFactory())) }
@Composable fun NegativeSize() { Text("x", Modifier.size((-1).dp)) }
fun paintFactory(): Color = Color.Red
@Composable fun EffectfulBackground() { Text("x", Modifier.background(paintFactory())) }
@Composable fun UnknownStringToken() { Text(UnknownTokens.label) }
@Composable fun UnknownColorToken() { Text("x", Modifier.background(UnknownTokens.color)) }
@Composable fun UnknownStyleToken() { Text("x", fontSize = UnknownTokens.fontSize) }
@Composable fun WeightWrongParent() {
    Row {
        val weighted = Modifier.weight(1f)
        Box { Text("x", weighted) }
    }
}
@Composable fun AlignWrongParent() {
    Box {
        val aligned = Modifier.align(Alignment.BottomEnd)
        Row { Text("x", aligned) }
    }
}
@Composable fun WeightWithoutFill() { Column { Text("x", Modifier.weight(1f, fill = false)) } }
@Composable fun InvalidFillFraction() { Text("x", Modifier.fillMaxWidth(2f)) }
