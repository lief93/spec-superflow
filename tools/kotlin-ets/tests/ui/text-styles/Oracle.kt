@file:Suppress("INVISIBLE_MEMBER", "INVISIBLE_REFERENCE")
package fontfixtures

import androidx.compose.ui.text.font.*
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.sp

fun main() {
    val style = heading(18.sp, family())
    println(listOf(style.fontSize.value, style.fontWeight!!.weight, style.lineHeight.value,
        style.color.toArgb().toUInt().toLong()).joinToString(","))
    val fonts = listOf(Font(R.font.normal, FontWeight(300)), Font(R.font.medium, FontWeight(500)),
        Font(R.font.normal, FontWeight(700)), Font(R.font.medium, FontWeight(400), FontStyle.Italic))
    for (italic in listOf(false, true)) {
        for (weight in listOf(100, 300, 350, 400, 450, 500, 550, 700, 900)) {
            val match = FontMatcher().matchFont(fonts, FontWeight(weight), if (italic) FontStyle.Italic else FontStyle.Normal).first()
            println("${match.weight.weight},${match.style.value}")
        }
    }
}
