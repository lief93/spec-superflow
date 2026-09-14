package crossfileoverloads

fun choose(value: Double, suffix: Int): Int = if (value > 0.0) 200 + suffix else 300 + suffix

fun keep(value: Int): Int = value + 2

fun choose_0(value: Int): Int = value
