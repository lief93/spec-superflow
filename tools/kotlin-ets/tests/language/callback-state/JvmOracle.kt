package callbackstate

fun main() {
    for ((seed, first, second) in listOf(
        Triple(0, 1, 2),
        Triple(3, 1, -2),
        Triple(-4, 8, -1),
        Triple(7, -3, 2),
    )) {
        println(callbackState(seed, first, second))
    }
}
