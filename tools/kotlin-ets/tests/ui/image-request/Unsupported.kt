package requestfixtures
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import coil.request.ImageRequest
import coil.decode.SvgDecoder

@Composable
fun customContext() = ImageRequest.Builder(LocalContext.current.applicationContext).build()
fun otherData(builder: ImageRequest.Builder) = builder.data(123).build()
fun otherDecoder(builder: ImageRequest.Builder) = builder.decoderFactory(SvgDecoder.Factory(false)).build()
fun otherOption(builder: ImageRequest.Builder) = builder.allowHardware(false).build()
