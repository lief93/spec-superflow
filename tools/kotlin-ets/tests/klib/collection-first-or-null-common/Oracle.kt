package collectionfirstornullcommon

private fun render(value: Int?): String = value?.toString() ?: "null"
private fun render(values: List<Int?>): String = values.joinToString(",") { render(it) }

fun main() {
    println(render(first(emptyList())))
    println(render(first(listOf(4, 5))))
    println(render(firstMatching(emptyList(), 2)))
    println(render(firstMatching(listOf(1, 2, 3), 2)))
    println(render(firstMatching(listOf(1, 2, 3), 9)))
    println(render(firstMatching(listOf(1, 2, 3), 1)))
}
