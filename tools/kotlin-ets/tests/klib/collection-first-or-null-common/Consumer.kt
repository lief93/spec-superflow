package collectionfirstornullcommon

fun first(values: Iterable<Int>): Int? = values.firstOrNull()

fun firstMatching(values: Iterable<Int>, sought: Int): List<Int?> {
    var callbacks = 0
    val result = values.firstOrNull { value ->
        callbacks += 1
        value == sought
    }
    return listOf(callbacks, result)
}
