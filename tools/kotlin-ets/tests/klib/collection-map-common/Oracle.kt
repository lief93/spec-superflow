package collectionmapcommon

private fun scenario(values: List<Int>): String =
    mapShift(values).joinToString(",") + "|" + mapEvenHalves(values).joinToString(",")

fun main() {
    println(scenario(listOf(1, 2, 3, 4)))
    println(scenario(emptyList()))
    println(scenario(listOf(Int.MIN_VALUE, -3, -2, 0, Int.MAX_VALUE)))
}
