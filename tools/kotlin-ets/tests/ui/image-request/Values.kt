package requestfixtures
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import coil.request.ImageRequest
import coil.decode.SvgDecoder

fun configure(builder: ImageRequest.Builder, url: String?, fade: Boolean): ImageRequest {
    return builder.data(url).decoderFactory(SvgDecoder.Factory()).crossfade(fade).build()
}
fun duration(builder: ImageRequest.Builder, millis: Int): ImageRequest = builder.crossfade(millis).build()
@Composable
fun request(url: String): ImageRequest = configure(ImageRequest.Builder(LocalContext.current), url, true)
