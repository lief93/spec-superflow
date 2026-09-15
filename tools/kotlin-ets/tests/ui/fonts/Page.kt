package fontfixtures
import androidx.compose.runtime.Composable
import androidx.compose.foundation.text.BasicText

@Composable fun Page() {
    val fonts = same(family(face()))
    BasicText("Font descriptors")
}
