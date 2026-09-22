package widgetsfixture

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Button
import androidx.compose.material3.Text as Label
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage

@Composable
fun Page(title: String, enabled: Boolean, onAction: () -> Unit, imageUrl: String,
    input: String, onInput: (String) -> Unit, surfaceColor: Color) {
    val identity = Modifier
    val frame = Modifier.width(120.dp).padding(4.dp).width(80.dp)
    Column(modifier = frame.then(identity)) {
        Label(title)
        Button(onClick = onAction, enabled = enabled,
            modifier = Modifier.padding(horizontal = 3.dp, vertical = 2.dp).height(40.dp)) {
            Row {
                Label("left")
                Box(modifier = Modifier.height(8.dp).then(Modifier.width(12.dp))) {
                    Label("right")
                }
            }
        }
        Label("after")
        Row(Modifier.padding(2.dp).width(60.dp)) { Label("reverse") }
        Box(Modifier.height(2.dp))
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
    }
}
