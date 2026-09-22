package collectionquantifierscommon

fun main() {
    println(anyValue(emptyList()))
    println(anyValue(listOf(1)))
    println(noneValue(emptyList()))
    println(noneValue(listOf(1)))
    println(anyMatching(emptyList(), 2))
    println(anyMatching(listOf(1, 2, 3), 2))
    println(allDifferent(emptyList(), 2))
    println(allDifferent(listOf(1, 2, 3), 2))
    println(allDifferent(listOf(1, 3), 2))
    println(noneMatching(emptyList(), 2))
    println(noneMatching(listOf(1, 2, 3), 2))
    println(noneMatching(listOf(1, 3), 2))
}
