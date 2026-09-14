package filtercases

fun positive(values: List<Int>): List<Int> = values.filter { it > 0 }
fun nonPositive(values: Iterable<Int>): List<Int> = values.filterNot { it > 0 }

fun <T> selected(values: List<T>, predicate: (T) -> Boolean): List<T> = values.filter(predicate)
fun <T> rejected(values: Iterable<T>, predicate: (T) -> Boolean): List<T> = values.filterNot(predicate)
fun nullableSelected(values: List<Int?>, keep: Boolean): List<Int?> = values.filter { keep }
fun nullableRejected(values: Iterable<Int?>, keep: Boolean): List<Int?> = values.filterNot { keep }
fun mutableSelected(values: MutableList<Int>): List<Int> = values.filter { it > 0 }
fun mutableRejected(values: MutableList<Int>): List<Int> = values.filterNot { it > 0 }

fun traceFilter(values: List<Int>, invert: Boolean, keep: Boolean): String {
    var count = 0
    var order = 0
    val predicate: (Int) -> Boolean = { value ->
        count = count + 1
        order = order * 10 + value
        keep
    }
    val result = if (invert) values.filterNot(predicate) else values.filter(predicate)
    return "$count/$order/${result.size}/${values.size}"
}

fun sourceAfterFilter(invert: Boolean): List<Int> {
    val values = mutableListOf(3, 1, 2)
    val result = if (invert) values.filterNot { it > 1 } else values.filter { it > 1 }
    values.add(9)
    return listOf(values.size, values[0], values[1], values[2], values[3], result.size, result[0])
}

fun filterReceiver(log: MutableList<Int>): List<Int> {
    log.add(1)
    return listOf(3, 1, 2)
}

fun filterPredicate(log: MutableList<Int>): (Int) -> Boolean {
    log.add(2)
    return { value ->
        log.add(value + 10)
        value > 1
    }
}

fun evaluationOrder(invert: Boolean): List<Int> {
    val log = mutableListOf<Int>()
    if (invert) filterReceiver(log).filterNot(filterPredicate(log))
    else filterReceiver(log).filter(filterPredicate(log))
    return log
}

fun explodingFilter(values: List<Int>, seen: MutableList<Int>, invert: Boolean): List<Int> {
    val predicate: (Int) -> Boolean = { value ->
        seen.add(value)
        1 / (value - 2) > 0
    }
    return if (invert) values.filterNot(predicate) else values.filter(predicate)
}

fun modifyingFilter(values: MutableList<Int>, invert: Boolean): List<Int> {
    val predicate: (Int) -> Boolean = { value ->
        values.add(value)
        true
    }
    return if (invert) values.filterNot(predicate) else values.filter(predicate)
}

fun emptyFilter(): List<Int> = listOf<Int>().filter { true }
fun emptyFilterNot(): List<Int> = listOf<Int>().filterNot { false }
