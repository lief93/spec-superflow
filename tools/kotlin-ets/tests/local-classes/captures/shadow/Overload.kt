package reviewoverload

fun `$seed`(value: Int): Int = value
fun `$seed`(value: String): Int = 10
fun result(seed: Int): Int {
    class Local(val `$seed`: Int) {
        val value = seed + `$seed`("text")
    }
    return Local(0).value
}
