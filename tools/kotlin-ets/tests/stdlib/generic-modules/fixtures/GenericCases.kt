package genericmodules

fun primitiveTransfer(first: Int, second: Int): Int =
    consumeNext(mappedCursor(listOf(first, second), { it + 1 }, { it > 0 }))

fun stringTransfer(first: Int, second: Int): String =
    consumeNext(mappedCursor(listOf(first, second), { it.toString() }, { it.length > 1 }))

fun objectTransfer(first: Int, second: Int): Int =
    consumeNext(mappedCursor(listOf(first, second), { GenericItem(it) }, { it.value > 0 })).value

fun boxedTransfer(value: Int): Int {
    val boxes = listOf(GenericBox(GenericItem(value)))
    return consumeNext(listCursor(preserved(boxes))).value.value
}

fun nullableTransfer(value: Int?): Int? = consumeNext(listCursor(preserved(listOf(value))))

fun arrayReplacement(first: Int, second: Int): Int {
    val values = arrayOf(GenericItem(first), GenericItem(second))
    val cursor = arrayCursor(values)
    consumeNext(cursor)
    replaceElement(values, 1, GenericItem(first + second))
    return consumeNext(cursor).value + arrayElement(values, 0).value
}

fun tracePipeline(trace: MutableList<Int>): Int {
    val cursor = mappedCursor(listOf(1, 2, 3), {
        trace.add(it)
        it + 10
    }, {
        trace.add(it)
        it > 11
    })
    return consumeNext(cursor) * 100 + consumeNext(cursor)
}

fun emptyPipeline(trace: MutableList<Int>): Boolean = cursorMore(mappedCursor(listOf<Int>(), {
    trace.add(it)
    it.toString()
}, {
    trace.add(it.length)
    true
}))

fun sourceUnmodified(): Int {
    val source = mutableListOf(1, 2, 3)
    val result = rejectList(transformList(source) { it + 10 }) { it > 12 }
    return source.size * 1000 + source[0] * 100 + result.size * 10 + result[0]
}

fun mapFailure(trace: MutableList<Int>): Int = consumeNext(mappedCursor(listOf(1, 2, 3), {
    trace.add(it)
    10 / (2 - it)
}, { true }))

fun filterFailure(trace: MutableList<Int>): Int = consumeNext(mappedCursor(listOf(1, 2, 3), { it }, {
    trace.add(it)
    10 / (2 - it) > 0
}))

fun mapMutation(values: MutableList<Int>, trace: MutableList<Int>): Int =
    transformList(values) {
        trace.add(it)
        values.add(9)
        it
    }.size

fun filterMutation(values: MutableList<Int>, trace: MutableList<Int>): Int =
    retainList(values) {
        trace.add(it)
        values.add(9)
        true
    }.size

fun cursorMutation(values: MutableList<Int>): Int {
    val cursor = listCursor(values)
    values.add(9)
    return consumeNext(cursor)
}

fun emptyCursor(): Int = consumeNext(listCursor(listOf<Int>()))
