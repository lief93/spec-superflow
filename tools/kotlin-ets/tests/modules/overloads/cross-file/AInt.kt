package crossfileoverloads

fun choose(value: Int, suffix: Int): Int = value * 10 + suffix

fun keep(value: Token): Token = value

fun forward(value: Int): Int = choose(value = value, suffix = 3)

fun uniqueName(value: Int): Int = value + 7
