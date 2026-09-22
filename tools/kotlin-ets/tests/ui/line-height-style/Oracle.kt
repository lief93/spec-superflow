package lineheightstyle

fun main() {
    semanticSnapshot().forEach(::println)
    println(heldCode(hold(makeLegacyStyle(
        androidx.compose.ui.text.style.LineHeightStyle.Alignment.Top,
        androidx.compose.ui.text.style.LineHeightStyle.Trim.Both,
    ))))
}
