package colorvalues

import androidx.compose.ui.graphics.Color

// Unary Long operations are not part of the literal ARGB constructor contract.
fun computedLong(): Color = Color(-1L)
