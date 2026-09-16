package degradation

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

var hits = 0
fun wrapping(): Boolean { hits++; return false }
fun label(): String = hits.toString()

@Composable fun NamedArguments() {
    Text(softWrap = wrapping(), text = label())
}

@Composable fun ExplicitLocal() {
    val wrap = wrapping()
    Text(softWrap = wrap, text = label())
}

@Composable fun UnsupportedNamedArgument() {
    Text(softWrap = System.getProperty("missing") != null, text = "Skipped")
}

@Composable fun RequiredNamedArgument() {
    Text(softWrap = false, text = android.os.Build.VERSION.SDK_INT.toString())
}
