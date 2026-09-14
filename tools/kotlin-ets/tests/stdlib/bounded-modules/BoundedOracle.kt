package boundedmodules

fun main() {
    fun record(name: String, arguments: String = "", action: (MutableList<Int>) -> Any?) {
        val trace = mutableListOf<Int>()
        val result = try { "value:" + action(trace).toString() }
            catch (failure: Exception) { "error:" + failure.javaClass.simpleName }
        println("$name|$arguments|$result|${trace.joinToString(",")}")
    }
    for (value in listOf(-3, 0, 7)) record("interfaceRead", "$value") { interfaceRead(value, it) }
    for ((first, second) in listOf(1 to 2, -1 to 3, -2 to -3, 0 to 0)) {
        record("filteredRead", "$first,$second") { filteredRead(first, second, it) }
        record("rejectedRead", "$first,$second") { rejectedRead(first, second, it) }
        record("classRead", "$first,$second") { classRead(first, second, it) }
    }
    for (value in listOf("", "bound", "value")) record("stringRead", value) { stringRead(value) }
    record("emptyRead") { emptyRead(it) }
    record("memberMapFailure") { memberMapFailure(it) }
    record("memberFilterFailure") { memberFilterFailure(it) }
    for (filter in listOf(false, true)) record("memberMutation", "$filter") { memberMutation(filter, it) }
    record("identity") { trace ->
        val first = BoundedNumber(3, trace)
        val second = BoundedNumber(-1, trace)
        val source = listOf(first, second)
        val retained = retainPositive(source)
        retained !== source && retained.size == 1 && retained[0] === first && source[1] === second && source.size == 2
    }
    for (filter in listOf(false, true)) record("errorIdentity", "$filter") { trace ->
        val marker = IllegalStateException("identity")
        val source = listOf(BoundedAction { trace.add(1); throw marker }, BoundedAction { trace.add(2); 2 })
        try {
            if (filter) retainPositive(source) else readValues<Int, BoundedAction>(source)
            false
        } catch (failure: IllegalStateException) { failure === marker }
    }
}
