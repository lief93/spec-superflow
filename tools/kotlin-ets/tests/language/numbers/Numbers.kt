package numbers

fun scaledGap(base: Double, scale: Double, extra: Double = 2.5): Double =
    (base * scale + extra) / 2.0 - base % 3.0

fun floatGap(seed: Int): Float = ((seed + 0.25f) * 2 - seed / 2f) % 7f
fun rounded(seed: Int): Float = (seed.toFloat() + 1f) - seed
fun literal(): Float = 0.1f
fun widened(): Double = literal().toDouble()
fun narrowed(value: Double): Float = value.toFloat()
fun integral(value: Double): Int = value.toInt()
fun floatIntegral(value: Float): Int = value.toInt()
fun doubleUnary(value: Double): Double { var next = value; val before = next++; return +before - --next }
fun floatUnary(value: Float): Float { var next = value; val before = next++; return -before + --next }
fun greater(left: Float, right: Float): Boolean = left > right
fun equal(left: Double, right: Double): Boolean = left == right

class Trace(var count: Int = 0) {
    fun read(): Double { count++; return count.toDouble() }
}
fun effects(): Double { val trace = Trace(); return trace.read() / trace.read() + trace.count }
