package consumer

import dependencies.adjusted

fun scenario(value: Int): Int = adjusted(value).let { it % 3 }
