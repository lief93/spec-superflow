package colorscheme

import androidx.compose.material3.ColorScheme
import androidx.compose.ui.graphics.toArgb

fun primaryOf(value: ColorScheme): Int = value.primary.toArgb()
