package imagecontrols

import androidx.compose.runtime.Composable
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage

@Composable fun MissingResource() { Image(painterResource(R.drawable.missing), null) }
@Composable fun NumericId() { Image(painterResource(123), null) }
@Composable fun DefaultIconTint() { Icon(painterResource(R.drawable.banner), null) }
@Composable fun UnsupportedScale() { Image(painterResource(R.drawable.banner), null, contentScale = ContentScale.FillWidth) }
@Composable fun UnsupportedFilter() { Image(painterResource(R.drawable.banner), null, colorFilter = ColorFilter.tint(Color.Red, BlendMode.Plus)) }
@Composable fun UnsupportedAlignment() { Image(painterResource(R.drawable.banner), null, alignment = Alignment.TopStart) }
@Composable fun NullableDescription(description: String? = null) { Image(painterResource(R.drawable.banner), description) }
fun nextSize(): Int = 20
@Composable fun EffectfulSize() { Image(painterResource(R.drawable.banner), null, Modifier.size(nextSize().dp)) }
@Composable fun FileUrl() { AsyncImage("file:///data/private/image.png", null) }
@Composable fun CredentialUrl() { AsyncImage("https://user:pass@example.invalid/image.png", null) }
@Composable fun DynamicModel(url: String = "https://example.invalid/image.png") { AsyncImage(url, null) }
@Composable fun LoadingCallback() { AsyncImage("https://example.invalid/image.png", null, onLoading = {}) }
