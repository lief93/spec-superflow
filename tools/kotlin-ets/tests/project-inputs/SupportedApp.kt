package collector

fun buttonLabel(page: Int): String = if (page < 3) "Next" else "Explore"

fun pageSpacing(base: Int, extra: Int): Int = base + extra
