package widgetsfixture

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Button
import androidx.compose.material3.Text as Label
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage

object KnownTokens {
    val label: String get() = error("mapped by project adapter")
    val brand: Color get() = error("mapped by project adapter")
    val titleSize: TextUnit get() = error("mapped by project adapter")
    val titleWeight: FontWeight get() = error("mapped by project adapter")
    val titleFamily: FontFamily get() = error("mapped by project adapter")
    val titleLineHeight: TextUnit get() = error("mapped by project adapter")
}

@Composable
fun Page(title: String, enabled: Boolean, onAction: () -> Unit, imageUrl: String,
    input: String, onInput: (String) -> Unit, surfaceColor: Color, lineHeight: TextUnit,
    fillFraction: Float, offsetX: Dp, borderWidth: Dp) {
    val identity = Modifier
    val frame = Modifier.width(120.dp).padding(4.dp).width(80.dp).fillMaxSize(fillFraction)
    Column(modifier = frame.then(identity)) {
        Label(title)
        Label(stringResource(R.string.title), modifier = Modifier.fillMaxWidth(0.5f),
            fontSize = 18.sp, fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace, lineHeight = lineHeight)
        Label(KnownTokens.label)
        Button(onClick = onAction, enabled = enabled,
            modifier = Modifier.background(KnownTokens.brand)
                .padding(horizontal = 3.dp, vertical = 2.dp).height(40.dp)) {
            Row(modifier = Modifier.weight(1f).fillMaxWidth()) {
                Label(stringResource(R.string.action), fontSize = KnownTokens.titleSize,
                    fontWeight = KnownTokens.titleWeight, fontFamily = KnownTokens.titleFamily,
                    lineHeight = KnownTokens.titleLineHeight)
                Box(modifier = Modifier.height(8.dp).then(Modifier.width(12.dp)).weight(2f)
                    .fillMaxHeight(0.5f)) {
                    Label("right", Modifier.align(Alignment.BottomEnd))
                }
            }
        }
        Label("after")
        Row(Modifier.weight(1f).padding(2.dp).width(60.dp).background(Color.Red)) { Label("reverse") }
        Box(Modifier.height(2.dp).background(Color(0xFF102030)))
        Label("callback", Modifier.size(width = 36.dp, height = 20.dp).background(surfaceColor)
            .clickable(enabled = enabled, onClick = onAction)
            .padding(start = 1.dp, top = 2.dp, end = 3.dp, bottom = 4.dp))
        Image(painterResource(R.drawable.logo), "Local image",
            Modifier.clickable(enabled = enabled, onClick = onAction)
                .background(surfaceColor).size(24.dp))
        AsyncImage(imageUrl, null, Modifier.width(32.dp).height(32.dp))
        TextField(value = input, onValueChange = onInput, enabled = enabled,
            modifier = Modifier.width(100.dp))
        BasicTextField(value = input, onValueChange = onInput, enabled = enabled,
            modifier = Modifier.width(90.dp))
        Label("ordered", Modifier.size(width = 48.dp, height = 24.dp).padding(2.dp)
            .offset(x = offsetX, y = (-2).dp)
            .background(surfaceColor, RoundedCornerShape(4.dp))
            .border(borderWidth, Color.Blue, CircleShape)
            .clip(RoundedCornerShape(3.dp))
            .clickable(enabled = enabled, onClick = onAction))
    }
}
