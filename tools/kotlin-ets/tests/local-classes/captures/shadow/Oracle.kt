package captureshadow

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(reviewglobal.result(seed))
        println(reviewoverload.result(seed))
        println(reviewimported.result(seed))
    }
}
