package widgethelpers

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun RecursiveCard() {
    RecursiveCard()
}

@Composable
fun RecursiveEntry() {
    RecursiveCard()
}

@Composable
fun <T> GenericCard(value: T) {
    Text(value.toString())
}

@Composable
fun GenericEntry() {
    GenericCard("value")
}

@Composable
fun DefaultContent(content: @Composable () -> Unit = { Text("default") }) {
    content()
}

@Composable
fun DefaultContentEntry() {
    DefaultContent()
}
