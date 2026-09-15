package colorscheme

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable fun Page() {
    val colors = scheme(false)
    Text("Scheme", color = colors.primary)
}
