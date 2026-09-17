package strings

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.text.BasicText
import androidx.compose.ui.res.stringResource

fun decorate(label: String): String = "[" + label + "]"
@Composable fun Page() {
    Column {
        BasicText(decorate(stringResource(R.string.title)))
        BasicText(stringResource(if (true) R.string.subtitle else R.string.title))
    }
}
@Composable fun Missing() { BasicText(stringResource(R.string.missing)) }
@Composable fun Styled() { BasicText(stringResource(R.string.styled)) }
class Label(val id: Int, vararg val args: Any) {
    @Composable fun text(): String = stringResource(id, *args)
}
@Composable fun Formatted() {
    Column {
        BasicText(Label(R.string.greeting, "Ada", 3).text())
        BasicText(Label(R.string.title).text())
    }
}
