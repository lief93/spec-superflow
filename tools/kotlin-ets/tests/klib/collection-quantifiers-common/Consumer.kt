package collectionquantifierscommon

fun anyValue(values: Iterable<Int>): Boolean = values.any()

fun noneValue(values: Iterable<Int>): Boolean = values.none()

fun anyMatching(values: Iterable<Int>, sought: Int): Int {
    var callbacks = 0
    val result = values.any { value ->
        callbacks += 1
        value == sought
    }
    return callbacks * 10 + if (result) 1 else 0
}

fun allDifferent(values: Iterable<Int>, blocked: Int): Int {
    var callbacks = 0
    val result = values.all { value ->
        callbacks += 1
        value != blocked
    }
    return callbacks * 10 + if (result) 1 else 0
}

fun noneMatching(values: Iterable<Int>, sought: Int): Int {
    var callbacks = 0
    val result = values.none { value ->
        callbacks += 1
        value == sought
    }
    return callbacks * 10 + if (result) 1 else 0
}
