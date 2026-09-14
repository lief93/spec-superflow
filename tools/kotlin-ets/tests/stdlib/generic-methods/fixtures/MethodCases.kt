package genericmethods

fun dispatchCase(mode: Int, trace: MutableList<Int>): String {
    val direct = MethodDerived<Int>(trace)
    val base: MethodBase<Int> = direct
    val contract: MethodProjector<Int> = direct
    val original = MethodBase<Int>(trace)
    val values = listOf(1, 2)
    val result = if (mode == 0) values.map { direct.project<String>(it) { trace.add(it); it.toString() } }
    else if (mode == 1) values.map { base.project<String>(it) { trace.add(it); it.toString() } }
    else if (mode == 2) values.map { contract.project<String>(it) { trace.add(it); it.toString() } }
    else values.map { original.project<String>(it) { trace.add(it); it.toString() } }
    return result[0] + ":" + result[1]
}

fun pipelineCase(trace: MutableList<Int>): Int {
    val pipeline = MethodPipeline<Int>(MethodDerived<Int>(trace))
    val cursor = pipeline.mapped<MethodItem>(listOf(1, 2, 3), {
        trace.add(it)
        MethodItem(it)
    }, {
        trace.add(100 + it.value)
        it.value > 1
    })
    val consumer = MethodConsumer()
    return consumer.next<MethodItem>(cursor).value * 100 + consumer.next<MethodItem>(cursor).value
}

fun emptyCase(trace: MutableList<Int>): Boolean {
    val cursor = MethodPipeline<Int>(MethodDerived<Int>(trace)).mapped<Int>(listOf<Int>(),
        { trace.add(it); it }, { trace.add(it); true })
    return MethodConsumer().more<Int>(cursor)
}

fun selectionCase(negate: Boolean, trace: MutableList<Int>): Int {
    val source = listOf(MethodItem(1), MethodItem(-2), MethodItem(3))
    val result = MethodPipeline<MethodItem>(MethodDerived<MethodItem>(trace)).selected(source,
        { trace.add(it.value); it.value > 0 }, negate)
    return result.size * 100 + result[0].value
}

fun polarityCase(mode: Int, trace: MutableList<Int>): Int =
    MethodPipeline<Int>(MethodBase<Int>(trace)).selected(listOf(1, 2, 3),
        { trace.add(it); mode > 1 }, mode == 1 || mode == 3).size

fun mutationCase(filter: Boolean, trace: MutableList<Int>): Int {
    val values = mutableListOf(1, 2, 3)
    val pipeline = MethodPipeline<Int>(MethodBase<Int>(trace))
    if (filter) return pipeline.selected(values, { trace.add(it); values.add(9); trace.add(values.size); true }, false).size
    return MethodConsumer().next<Int>(pipeline.mapped<Int>(values,
        { trace.add(it); values.add(9); trace.add(values.size); it }, { true }))
}

fun failureCase(filter: Boolean, trace: MutableList<Int>): Int {
    val pipeline = MethodPipeline<Int>(MethodBase<Int>(trace))
    val values = listOf(1, 2, 3)
    if (filter) return pipeline.selected(values, { trace.add(it); 12 / (2 - it) > 0 }, false).size
    return MethodConsumer().next<Int>(pipeline.mapped<Int>(values, { trace.add(it); 12 / (2 - it) }, { true }))
}

fun cursorCase(change: Boolean, trace: MutableList<Int>): Int {
    val values = mutableListOf(1, 2)
    val cursor = MethodPipeline<Int>(MethodBase<Int>(trace)).cursor(values)
    if (change) { values.add(3); trace.add(values.size) }
    val consumer = MethodConsumer()
    trace.add(consumer.next<Int>(cursor))
    trace.add(consumer.next<Int>(cursor))
    return consumer.next<Int>(cursor)
}

fun makeMethodProjector(trace: MutableList<Int>): MethodProjector<Int> { trace.add(1); return MethodDerived<Int>(trace) }
fun methodArgument(trace: MutableList<Int>): Int { trace.add(2); return 7 }
fun methodTransform(trace: MutableList<Int>): (Int) -> Int { trace.add(3); return { trace.add(4); it + 1 } }
fun receiverOnce(trace: MutableList<Int>): Int =
    makeMethodProjector(trace).project<Int>(methodArgument(trace), methodTransform(trace))
