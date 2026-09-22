package strings

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.text.BasicText
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource

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
class PluralLabel(val id: Int, val count: Int, vararg val args: Any) {
    @Composable fun text(): String = pluralStringResource(id, count, *args)
}
@Composable fun Formatted() {
    Column {
        BasicText(stringResource(R.string.greeting, "Ada", 3))
        BasicText(Label(R.string.greeting, "Ada", 3).text())
        BasicText(PluralLabel(R.plurals.photos, 2, 2).text())
        BasicText(Label(R.string.title).text())
    }
}
@Composable fun Plural() { BasicText(pluralStringResource(R.plurals.photos, 2, 2)) }
@Composable fun MissingPlural() { BasicText(pluralStringResource(R.plurals.missing, 2)) }
@Composable fun Unknown() { BasicText(stringResource(999)) }
@Composable fun ArrayValue() { BasicText(R.array.labels.toString()) }
@Composable fun MissingArray() { BasicText(R.array.missing.toString()) }
