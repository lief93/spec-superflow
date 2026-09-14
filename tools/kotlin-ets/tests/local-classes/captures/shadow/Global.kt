package reviewglobal

fun `$seed`(): Int = 10
fun result(seed: Int): Int {
    class Local {
        val value = seed + `$seed`()
    }
    return Local().value
}
