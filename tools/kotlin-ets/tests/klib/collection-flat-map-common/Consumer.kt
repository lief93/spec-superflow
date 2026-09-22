package collectionflatmapcommon

fun flatMapTrace(values: Iterable<Int>): List<Int> {
    var callbacks = 0
    return values.flatMap { value ->
        callbacks += 1
        if (value == 0) listOf<Int>() else listOf(callbacks, value, -value)
    }
}
