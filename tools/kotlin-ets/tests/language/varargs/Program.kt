package varargs

fun rewrite(vararg values: Int): Int {
    if (values.size == 0) return 0
    values[0] = 9
    return values.size
}

fun singleSpread(): Int {
    val values = intArrayOf(1, 2)
    val size = rewrite(*values)
    return values[0] * 10 + size
}

fun mutate(values: IntArray): Int { values[0] = 7; return 3 }
fun digits(vararg values: Int): Int {
    var result = 0
    for (value in values) result = result * 10 + value
    return result
}
fun mixed(): Int {
    val values = intArrayOf(1, 2)
    return digits(0, *values, mutate(values), 4)
}
class Values(vararg val values: String)
fun model(): String = Values("first", "second").values[1]
fun empty(): Int = rewrite()
