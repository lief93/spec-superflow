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
@Composable fun Formatted() { BasicText(stringResource(R.string.title, "argument")) }
