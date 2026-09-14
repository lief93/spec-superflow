package genericmethods

fun main() {
    fun record(name: String, arguments: String = "", action: (MutableList<Int>) -> Any?) {
        val trace = mutableListOf<Int>()
        val result = try { "value:" + action(trace).toString() }
            catch (failure: Exception) { "error:" + failure.javaClass.simpleName }
        println("$name|$arguments|$result|${trace.joinToString(",")}")
    }
    for (mode in 0..3) record("dispatchCase", "$mode") { dispatchCase(mode, it) }
    record("pipelineCase") { pipelineCase(it) }
    record("emptyCase") { emptyCase(it) }
    for (negate in listOf(false, true)) record("selectionCase", "$negate") { selectionCase(negate, it) }
    for (mode in 0..3) record("polarityCase", "$mode") { polarityCase(mode, it) }
    for (filter in listOf(false, true)) record("mutationCase", "$filter") { mutationCase(filter, it) }
    for (filter in listOf(false, true)) record("failureCase", "$filter") { failureCase(filter, it) }
    for (change in listOf(false, true)) record("cursorCase", "$change") { cursorCase(change, it) }
    record("receiverOnce") { receiverOnce(it) }
    record("identity") { trace ->
        val first = MethodItem(3)
        val second = MethodItem(-1)
        val source = listOf(first, second)
        val retained = MethodPipeline<MethodItem>(MethodDerived<MethodItem>(trace)).selected(source,
            { trace.add(it.value); it.value > 0 }, false)
        retained !== source && retained.size == 1 && retained[0] === first && source.size == 2 && source[1] === second
    }
    for (filter in listOf(false, true)) record("errorIdentity", "$filter") { trace ->
        val marker = IllegalStateException("identity")
        val pipeline = MethodPipeline<Int>(MethodDerived<Int>(trace))
        val source = listOf(1, 2)
        try {
            if (filter) pipeline.selected(source, { trace.add(it); throw marker }, false)
            else pipeline.mapped<Int>(source, { trace.add(it); throw marker }, { true })
            false
        } catch (failure: IllegalStateException) { failure === marker }
    }
}
