package lineheightstyle

import androidx.compose.ui.text.style.LineHeightStyle

class StyleHolder(val style: LineHeightStyle)

fun hold(value: LineHeightStyle): StyleHolder = StyleHolder(value)

fun heldCode(value: StyleHolder): Int = styleCode(value.style)
