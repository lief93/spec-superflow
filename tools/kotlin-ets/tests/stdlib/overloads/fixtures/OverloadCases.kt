package stdliboverloads

fun numericCase(mode: Int, trace: MutableList<Int>): Int {
    val selector = OverloadSelector(trace)
    val result = if (mode == 0) overloadMapped(listOf(1, 2)) { choose(it, trace) }
    else if (mode == 1) overloadMapped(listOf(1.0, 2.0)) { choose(it, trace) }
    else if (mode == 2) overloadMapped(listOf(1, 2)) { selector.select(it) }
    else overloadMapped(listOf(1.0, 2.0)) { selector.select(it) }
    return result[0] * 100 + result[1]
}

fun overloadValues(trace: MutableList<Int>): List<Int> { trace.add(1); return listOf(1, 2) }
fun overloadTransform(trace: MutableList<Int>): (Int) -> Int {
    trace.add(2)
    return { trace.add(10 + it); choose(it, trace) }
}
fun overloadPredicate(trace: MutableList<Int>): (Int) -> Boolean {
    trace.add(3)
    return { trace.add(30 + it); true }
}
fun onceCase(trace: MutableList<Int>): Int {
    val cursor = overloadCursor(overloadFiltered(
        overloadMapped(overloadValues(trace), overloadTransform(trace)), overloadPredicate(trace), false))
    trace.add(overloadNext(cursor))
    return overloadNext(cursor)
}

fun overloadReceiver(trace: MutableList<Int>): OverloadSelector { trace.add(1); return OverloadSelector(trace) }
fun overloadArgument(value: Int, trace: MutableList<Int>): Int { trace.add(2); return value }
fun receiverOnce(trace: MutableList<Int>): Int {
    val result = overloadMapped(listOf(1, 2)) { overloadReceiver(trace).select(overloadArgument(it, trace)) }
    return result[0] + result[1]
}

fun emptyCase(mode: Int, trace: MutableList<Int>): Boolean {
    val values = if (mode == 0) overloadMapped(listOf<Int>()) { choose(it, trace) }
    else overloadMapped(listOf<Double>()) { choose(it, trace) }
    return overloadMore(overloadCursor(overloadFiltered(values, { trace.add(it); true }, false)))
}

fun polarityCase(mode: Int, trace: MutableList<Int>): Int {
    val selector = OverloadSelector(trace)
    val negate = mode == 1 || mode == 3
    if (mode == 0 || mode == 2) return overloadFiltered(listOf(1, 2, 3),
        { selector.accept(it, mode > 1) }, negate).size
    return overloadFiltered(listOf(1.0, 2.0, 3.0), { selector.accept(it, mode > 1) }, negate).size
}

fun mutationCase(filter: Boolean, trace: MutableList<Int>): Int {
    val values = mutableListOf(1, 2, 3)
    if (filter) return overloadFiltered(values,
        { choose(it, trace); values.add(9); trace.add(values.size); true }, false).size
    return overloadMapped(values, { choose(it, trace); values.add(9); trace.add(values.size); it }).size
}

fun failureCase(filter: Boolean, trace: MutableList<Int>): Int {
    val values = listOf(1, 0, 2)
    if (filter) return overloadFiltered(values, { choose(it, trace) > 0 }, false).size
    return overloadMapped(values) { choose(it, trace) }.size
}

fun cursorCase(change: Boolean, trace: MutableList<Int>): Int {
    val values = mutableListOf(1, 2)
    val cursor = overloadCursor(values)
    if (change) { values.add(3); trace.add(values.size) }
    trace.add(overloadNext(cursor))
    trace.add(overloadNext(cursor))
    return overloadNext(cursor)
}

fun objectPipeline(values: List<OverloadItem>, trace: MutableList<Int>): List<OverloadItem> =
    overloadFiltered(overloadMapped(values) { choose(it.value, trace); it },
        { trace.add(it.value); it.value > 1 }, false)

fun errorPipeline(values: List<Int>, transform: (Int) -> Int, predicate: (Int) -> Boolean, filter: Boolean): List<Int> =
    if (filter) overloadFiltered(values, predicate, false) else overloadMapped(values, transform)
