package doublerelations

fun main() {
    val values = listOf(Double.NEGATIVE_INFINITY, -1.0, -0.0, 0.0, 1.0, Double.POSITIVE_INFINITY, Double.NaN)
    val operations = listOf("less" to ::less, "lessEqual" to ::lessEqual, "greater" to ::greater, "greaterEqual" to ::greaterEqual)
    for ((name, operation) in operations) for ((leftIndex, left) in values.withIndex()) for ((rightIndex, right) in values.withIndex()) {
        val trace = mutableListOf<Int>()
        val result = operation(left, right, trace)
        println("$name|$leftIndex,$rightIndex|$result|${trace.joinToString(",")}")
    }
}
