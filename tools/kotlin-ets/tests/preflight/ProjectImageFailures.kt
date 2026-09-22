package preflightfixture

import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.painterResource

object R {
    object drawable {
        const val selector: Int = 0x7f040001
        const val missing: Int = 0x7f040002
        const val supported: Int = 0x7f040003
    }
}

@Composable
fun UnsupportedProjectImage() {
    Image(painterResource(R.drawable.selector), null)
}

@Composable
fun MissingProjectImage() {
    Image(painterResource(R.drawable.missing), null)
}

@Composable
fun SupportedProjectImage() {
    Image(painterResource(R.drawable.supported), null)
}
