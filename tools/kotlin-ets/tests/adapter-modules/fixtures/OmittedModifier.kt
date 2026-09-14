package demo.adapters

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun Frame(label: String, modifier: Modifier = Modifier.width(120.dp), content: @Composable () -> Unit) {
    Column(modifier) {
        BasicText(label)
        content()
    }
}

@Composable
fun OmittedModifierPage() {
    Frame("Title") {}
}
