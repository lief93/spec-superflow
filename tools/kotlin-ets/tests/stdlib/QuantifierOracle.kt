package quantifiercases

private fun json(values: List<Int?>) = values.joinToString(",", "[", "]") { it?.toString() ?: "null" }
fun main() {
    val inputs = listOf(emptyList(), listOf(null), listOf(-1), listOf(1), listOf(-1, 2, 0),
        listOf(1, -2, 3), listOf(null, 0, 2), listOf(1, 2, 3))
    for (operation in 0..3) for (input in inputs) for (mode in 0..4) for (trigger in 1..3) {
        val values = input.toMutableList()
        val trace = mutableListOf<Int>()
        val result = try { quantify(operation, values, mode, trigger, trace) }
            catch (failure: IndexOutOfBoundsException) { "IndexOutOfBoundsException" }
            catch (failure: ConcurrentModificationException) { "ConcurrentModificationException" }
        println("{\"operation\":$operation,\"input\":${json(input)},\"mode\":$mode,\"trigger\":$trigger," +
            "\"result\":\"$result\",\"trace\":${json(trace)},\"values\":${json(values)}}")
    }
}
