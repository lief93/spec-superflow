package collectionflatmapcommon

fun main() {
    println(flatMapTrace(listOf(1, 0, 2)).joinToString(","))
    println(flatMapTrace(emptyList()).joinToString(","))
    println(flatMapTrace(listOf(-2, 3)).joinToString(","))
}
