package fontfixtures

import androidx.compose.ui.text.font.*

var reads = 0
fun face(): Font { reads += 1; return Font(R.font.normal, FontWeight.Normal) }
fun family(font: Font): FontFamily = FontFamily(font, Font(R.font.medium, FontWeight.Medium))
fun same(value: FontFamily): FontFamily = value
fun observations(): List<Int> {
    val font = face()
    val fonts = same(family(font))
    return listOf(font.weight.weight, Font(R.font.medium, FontWeight.Medium).weight.weight,
        FontWeight(450).weight, reads)
}
