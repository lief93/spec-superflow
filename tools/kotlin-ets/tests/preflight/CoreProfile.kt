package preflightfixture

fun localStep(value: Int): Int = value + 1

fun withSourceDefault(value: Int = 7): String = localStep(value).toString()

fun coreProfile(): String = withSourceDefault()
