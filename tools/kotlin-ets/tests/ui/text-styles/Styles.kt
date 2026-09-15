package fontfixtures

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.*
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.*

fun family(): FontFamily = FontFamily(Font(R.font.normal), Font(R.font.medium, FontWeight.Medium))
fun heading(size: TextUnit, font: FontFamily): TextStyle = TextStyle(fontSize = size,
    fontFamily = font, fontWeight = FontWeight.Medium, lineHeight = 28.sp,
    color = Color(0xFF156340), textAlign = TextAlign.Center)
