package demo.adapters

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun Frame(label: String, modifier: Modifier, content: @Composable () -> Unit) {
    Column(modifier) {
        BasicText(label)
        content()
    }
}

@Composable
fun AdapterPage() {
    Frame("Independent adapter", Modifier.width(120.dp).testTag("adapter-frame")) {
        Box(Modifier.width(24.dp).testTag("adapter-content"))
    }
}
