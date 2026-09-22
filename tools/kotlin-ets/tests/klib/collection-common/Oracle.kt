package collectioncommon

private fun scenario(values: List<Int>): String =
    filterEven(values).joinToString(",") + "|" + filterOdd(values).joinToString(",")

fun main() {
    println(scenario(listOf(1, 2, 3, 4)))
    println(scenario(emptyList()))
    println(scenario(listOf(Int.MIN_VALUE, -3, -2, 0, Int.MAX_VALUE)))
}
