package privateoverloads

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) println(privateCase(seed))
}
