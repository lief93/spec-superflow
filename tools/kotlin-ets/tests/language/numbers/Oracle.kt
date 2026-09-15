package numbers

fun emit(value: Number) {
    val number = value.toDouble()
    println(if (number.isNaN()) "NaN" else java.lang.Long.toHexString(java.lang.Double.doubleToRawLongBits(number)).padStart(16, '0'))
}
fun main() {
    for (seed in listOf(0, -3, 7, 16777217, Int.MAX_VALUE)) {
        emit(layoutWidth(seed)); emit(floatGap(seed)); emit(rounded(seed))
    }
    emit(literal()); emit(widened()); emit(effects())
    for (value in listOf(0.0, -0.0, -3.75, 1.0 / 3.0, 1e30, Double.POSITIVE_INFINITY, Double.NaN)) {
        emit(narrowed(value)); emit(integral(value)); emit(floatIntegral(value.toFloat()))
        emit(doubleUnary(value)); emit(floatUnary(value.toFloat()))
        println(greater(value.toFloat(), 0f)); println(equal(value, value))
    }
}
