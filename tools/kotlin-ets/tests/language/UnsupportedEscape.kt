package languagefixture

fun returnAcrossExpression(flag: Boolean): Int {
    val value = if (flag) {
        if (flag) return 7
        2
    } else 3
    return value + 10
}
