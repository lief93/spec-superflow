package reviewimported

fun result(seed: Int): Int {
    class Local(val `$seed`: Int) {
        val value = seed + `$seed`("text")
    }
    return Local(0).value
}
