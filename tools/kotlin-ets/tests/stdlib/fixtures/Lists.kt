package stdlibcases

fun emptySize(): Int = listOf<Int>().size
fun singleton(value: Int): Int = listOf(value)[0]
fun listRead(a: Int, b: Int, index: Int): Int = listOf(a, b)[index]
fun listSize(a: String, b: String): Int = listOf(a, b).size
fun containsInt(value: Int): Boolean = value in listOf(1, 2, 3)
fun containsString(value: String): Boolean = listOf("alpha", "beta").contains(value)
fun append(value: Int): Boolean = mutableListOf(1, 2).add(value)
fun emptyMutableAdd(value: Int): Boolean = mutableListOf<Int>().add(value)
fun indexed(values: List<Int>, index: Int): Int = values[index]
fun mapped(value: Int): Int = listOf(1, 2, 3).map { it + value }[2]
fun mutation(value: Int): Int {
    val values = mutableListOf(1, 2)
    values.add(value)
    return values[2] + values.size
}

fun invalidMap(): List<Int> {
    val values = mutableListOf(1, 2)
    return values.map { value ->
        values.add(value)
        value
    }
}

fun mappedIterable(value: Int): Int = mappedIterableValues(listOf(1, 2, 3), value)
fun mappedIterableValues(values: Iterable<Int>, value: Int): Int = values.map { it + value }[2]
fun mappedSet(value: Int): Int = setOf(1, 2, 3).map { it + value }[2]
fun mappedMutableSet(value: Int): Int {
    val values = mutableSetOf(1, 2)
    values.add(3)
    return values.map { it + value }[2]
}
fun invalidSetMap(): List<Int> {
    val values = mutableSetOf(1, 2)
    return values.map { value ->
        values.add(value + 10)
        value
    }
}
