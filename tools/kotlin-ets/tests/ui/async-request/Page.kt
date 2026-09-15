package asyncimages

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalInspectionMode
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import coil.decode.SvgDecoder

@Composable
fun request(url: String?): ImageRequest = ImageRequest.Builder(LocalContext.current)
    .data(url).decoderFactory(SvgDecoder.Factory()).crossfade(600).build()

@Composable
fun inspectionPlaceholder(id: Int) = if (LocalInspectionMode.current) painterResource(id) else null

@Composable
fun Picture(url: String?) {
    AsyncImage(url, contentDescription = null, placeholder = painterResource(R.drawable.logo), modifier = Modifier.size(96.dp))
}

var calls = 0
fun counted(value: Int): String { calls += 1; return value.toString() }
@Composable fun Maybe(label: String, show: Boolean) { if (show) Text(label) }
@Composable fun UnsafeArgument() {
    val index = remember { mutableStateOf(0) }
    Maybe(counted(index.value), false)
}

@Composable
fun Page() {
    val index = remember { mutableStateOf(0) }
    Column {
        Picture(if (index.value == 0) "http://127.0.0.1:18987/a.svg" else "http://127.0.0.1:18987/b.svg")
        AsyncImage(request(null), contentDescription = null, placeholder = inspectionPlaceholder(R.drawable.logo), modifier = Modifier.size(24.dp))
        Button(onClick = { index.value = 1 }) { Text("Change") }
    }
}

@Composable fun Unbounded() { AsyncImage(request("https://example.com/a.svg"), contentDescription = null) }
@Composable fun UnsupportedCallback() {
    AsyncImage(request("https://example.com/a.svg"), contentDescription = null, modifier = Modifier.size(20.dp), onSuccess = {})
}
