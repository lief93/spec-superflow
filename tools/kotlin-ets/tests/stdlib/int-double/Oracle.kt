package intdouble

fun main() {
    fun record(name: String, input: Int, action: (MutableList<Int>) -> Double) {
        val trace = mutableListOf<Int>()
        val result = try { "bits:" + java.lang.Long.toHexString(java.lang.Double.doubleToRawLongBits(action(trace))) }
            catch (failure: Exception) { "error:" + failure.javaClass.simpleName }
        println("$name|$input|$result|${trace.joinToString(",")}")
    }
    for (value in listOf(Int.MIN_VALUE, -2147483647, -16777217, -16777216, -1, 0, 1, 16777216, 16777217, 2147483646, Int.MAX_VALUE))
        record("widen", value) { widen(value, it) }
    for (value in listOf(-1, 0, 1)) record("receiverOnce", value) { receiverOnce(value, it) }
}
