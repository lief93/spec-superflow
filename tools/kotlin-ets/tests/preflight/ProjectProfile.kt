package preflightfixture

import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
import androidx.compose.ui.tooling.preview.Preview

@Preview
@Composable
fun ProjectProfilePreview() {
    Text("Project profile")
}

fun declarationOutsideUi(label: String) = object : Runnable {
    val normalized = label.uppercase()
    override fun run() = Unit
}
