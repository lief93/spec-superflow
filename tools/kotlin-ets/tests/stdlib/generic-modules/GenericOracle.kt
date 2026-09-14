package genericmodules

fun main() {
    fun record(name: String, arguments: String = "", block: (MutableList<Int>, MutableList<Int>) -> Any?) {
        val trace = mutableListOf<Int>()
        val values = mutableListOf(1, 2, 3)
        val result = try { "value:" + block(trace, values).toString() }
            catch (failure: Exception) { "error:" + failure.javaClass.simpleName }
        println("$name|$arguments|$result|${trace.joinToString(",")}|${values.joinToString(",")}")
    }
    for ((first, second) in listOf(1 to 20, -3 to 12, 0 to 99, -5 to -2)) {
        record("primitiveTransfer", "$first,$second") { _, _ -> primitiveTransfer(first, second) }
        record("stringTransfer", "$first,$second") { _, _ -> stringTransfer(first, second) }
        record("objectTransfer", "$first,$second") { _, _ -> objectTransfer(first, second) }
        record("arrayReplacement", "$first,$second") { _, _ -> arrayReplacement(first, second) }
    }
    for (value in listOf(-7, 0, 21)) record("boxedTransfer", "$value") { _, _ -> boxedTransfer(value) }
    for (value in listOf(null, -7, 0, 21)) record("nullableTransfer", "$value") { _, _ -> nullableTransfer(value) }
    record("tracePipeline") { trace, _ -> tracePipeline(trace) }
    record("emptyPipeline") { trace, _ -> emptyPipeline(trace) }
    record("sourceUnmodified") { _, _ -> sourceUnmodified() }
    record("mapFailure") { trace, _ -> mapFailure(trace) }
    record("filterFailure") { trace, _ -> filterFailure(trace) }
    record("mapMutation") { trace, values -> mapMutation(values, trace) }
    record("filterMutation") { trace, values -> filterMutation(values, trace) }
    record("cursorMutation") { _, values -> cursorMutation(values) }
    record("emptyCursor") { _, _ -> emptyCursor() }
}
