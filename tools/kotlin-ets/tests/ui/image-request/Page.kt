package requestfixtures
import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
import coil.request.ImageRequest

fun consume(request: ImageRequest): String = "request retained"
@Composable
fun Page() { Text(consume(request("https://example.com/avatar.svg"))) }
