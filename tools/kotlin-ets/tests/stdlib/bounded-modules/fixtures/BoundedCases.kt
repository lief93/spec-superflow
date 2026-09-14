package boundedmodules

fun interfaceRead(value: Int, trace: MutableList<Int>): Int {
    val values = listOf(BoundedNumber(value, trace), BoundedNumber(value + 1, trace))
    val result = readValues<Int, BoundedNumber>(values)
    return result[0] * 100 + result[1]
}

fun filteredRead(first: Int, second: Int, trace: MutableList<Int>): Int =
    nextRead<Int, BoundedNumber>(keptCursor(listOf(BoundedNumber(first, trace), BoundedNumber(second, trace))))

fun rejectedRead(first: Int, second: Int, trace: MutableList<Int>): Int =
    nextRead<Int, BoundedNumber>(boundedCursor<Int, BoundedNumber>(
        rejectPositive(listOf(BoundedNumber(first, trace), BoundedNumber(second, trace)))))

fun classRead(first: Int, second: Int, trace: MutableList<Int>): Int {
    val values = listOf(BoundedBase(first, trace), BoundedBase(second, trace))
    val result = readClasses(values)
    return result[0] + nextClass(classCursor(retainClasses(values)))
}

fun stringRead(value: String): String =
    readValues<String, BoundedText>(listOf(BoundedText(value)))[0]

fun emptyRead(trace: MutableList<Int>): Int {
    val values = listOf<BoundedNumber>()
    val mapped = readValues<Int, BoundedNumber>(values)
    val filtered = retainPositive(values)
    trace.add(mapped.size)
    trace.add(filtered.size)
    return mapped.size + filtered.size
}

fun memberMapFailure(trace: MutableList<Int>): Int =
    readValues<Int, BoundedFailure>(listOf(BoundedFailure(1, trace), BoundedFailure(2, trace), BoundedFailure(3, trace))).size

fun memberFilterFailure(trace: MutableList<Int>): Int =
    retainPositive(listOf(BoundedFailure(1, trace), BoundedFailure(2, trace), BoundedFailure(3, trace))).size

fun memberMutation(filter: Boolean, trace: MutableList<Int>): Int {
    val values = mutableListOf<BoundedMutator>()
    val extra = BoundedMutator(9, trace, {})
    values.add(BoundedMutator(1, trace, { values.add(extra); trace.add(values.size) }))
    return if (filter) retainPositive(values).size else readValues<Int, BoundedMutator>(values).size
}
