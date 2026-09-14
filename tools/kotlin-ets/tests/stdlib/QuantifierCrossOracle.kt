package quantifiercases

fun main() {
    val log = mutableListOf<Int>()
    println(orderedAny(log))
    println(log.joinToString(","))
    println(crossFileNullable(listOf(null, 1, null)))
    println(crossFileStrings(listOf("go", "stop", "later")))
    println(crossFileStrings(emptyList()))
    println(listAny(listOf(-1, 2, 3)) { it > 0 })
    println(mutableAll(mutableListOf(1, 2, 3)) { it > 0 })
}
