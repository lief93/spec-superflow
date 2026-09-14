package quantifiercases

fun quantify(operation: Int, values: MutableList<Int?>, mode: Int, trigger: Int, trace: MutableList<Int>): String {
    val predicate: (Int?) -> Boolean = { value ->
        trace.add(value ?: -99)
        if (mode == 3 && trace.size == trigger) listOf(1)[2]
        if (mode == 4 && trace.size == trigger) values.add(7)
        if (mode == 1) true else if (mode == 2) false else value != null && value > 0
    }
    return if (operation == 0) anyMatch(values, predicate).toString()
        else if (operation == 1) allMatch(values, predicate).toString()
        else if (operation == 2) noneMatch(values, predicate).toString()
        else countMatches(values, predicate).toString()
}

fun crossFileNullable(values: List<Int?>): Int = countMatches(values) { it == null }
fun crossFileStrings(values: List<String>): Boolean = noneMatch(values) { it == "stop" }
