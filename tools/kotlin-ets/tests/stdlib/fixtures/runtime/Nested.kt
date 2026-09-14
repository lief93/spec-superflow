package runtimedependencies

class Calculator(val divisor: Int) {
    val initial: Int = 12 / divisor
    fun quotient(value: Int): Int = divide(value, divisor)
    fun remainder(value: Int): Int = value % divisor
    fun mapped(value: Int): Int = listOf(value).map { it / divisor }[0]
}

fun nestedResult(value: Int): Int = Calculator(3).mapped(value)
fun classResult(value: Int): Int = Calculator(3).quotient(value) + Calculator(3).remainder(value)
