package collectionmapindexedcommon

private fun scenario(values: List<Int>): String =
    mapIndexedSum(values).joinToString(",") + "|" + mapIndexedEvenOffsets(values).joinToString(",")

fun main() {
    println(scenario(listOf(1, 2, 3, 4)))
    println(scenario(emptyList()))
    println(scenario(listOf(Int.MIN_VALUE, -3, -2, 0, Int.MAX_VALUE)))
}
