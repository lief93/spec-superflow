package stdliboverloads

fun main() {
    fun record(name: String, arguments: String = "", action: (MutableList<Int>) -> Any?) {
        val trace = mutableListOf<Int>()
        val result = try { "value:" + action(trace).toString() }
            catch (failure: Exception) { "error:" + failure.javaClass.simpleName }
        println("$name|$arguments|$result|${trace.joinToString(",")}")
    }
    for (mode in 0..3) record("numericCase", "$mode") { numericCase(mode, it) }
    record("onceCase") { onceCase(it) }
    record("receiverOnce") { receiverOnce(it) }
    for (mode in 0..1) record("emptyCase", "$mode") { emptyCase(mode, it) }
    for (mode in 0..3) record("polarityCase", "$mode") { polarityCase(mode, it) }
    for (filter in listOf(false, true)) record("mutationCase", "$filter") { mutationCase(filter, it) }
    for (filter in listOf(false, true)) record("failureCase", "$filter") { failureCase(filter, it) }
    for (change in listOf(false, true)) record("cursorCase", "$change") { cursorCase(change, it) }
    record("identity") { trace ->
        val first = OverloadItem(1)
        val second = OverloadItem(2)
        val values = listOf(first, second)
        val result = objectPipeline(values, trace)
        result !== values && result.size == 1 && result[0] === second &&
            values.size == 2 && values[0] === first && values[1] === second
    }
    for (filter in listOf(false, true)) record("errorIdentity", "$filter") { trace ->
        val marker = IllegalStateException("identity")
        val transform: (Int) -> Int = { choose(it, trace); throw marker }
        val predicate: (Int) -> Boolean = { choose(it, trace); throw marker }
        try { errorPipeline(listOf(1, 2), transform, predicate, filter); false }
        catch (failure: IllegalStateException) { failure === marker }
    }
}
