package stdlibcases

fun arithmetic(a: Int, b: Int): Int = ((a + b) * (a - b)) / b + a % b
fun sum(a: Int, b: Int): Int = a + b
fun product(a: Int, b: Int): Int = a * b
fun quotient(a: Int, b: Int): Int = a / b
fun remainder(a: Int, b: Int): Int = a % b
fun less(a: Int, b: Int): Boolean = a < b
fun lessEqual(a: Int, b: Int): Boolean = a <= b
fun greater(a: Int, b: Int): Boolean = a > b
fun greaterEqual(a: Int, b: Int): Boolean = a >= b
fun unary(a: Int): Int = -a + +a
fun comparisons(a: Int, b: Int): Boolean = a < b || a <= b || a > b || a >= b || a == b || a != b
fun compareValues(a: Int, b: Int): Int = a.compareTo(b)
fun booleanOps(a: Boolean, b: Boolean): Boolean = a.and(b).or(a.xor(b)).not()
fun eagerAnd(values: MutableList<Int>, a: Boolean): Boolean = a.and(values.add(5))
fun eagerOr(values: MutableList<Int>, a: Boolean): Boolean = a.or(values.add(5))
fun stringOps(s: String, n: Int): String = s + n.toString() + true.toString()
fun interpolation(s: String, n: Int): String = "$s:$n:${n > 0}"
fun length(s: String): Int = s.length
fun substring(s: String, start: Int, end: Int): String = s.substring(start, end)
fun suffix(s: String, start: Int): String = s.substring(start)
fun contains(s: String, part: String): Boolean = s.contains(part)
fun startsWith(s: String, part: String): Boolean = s.startsWith(part)
fun endsWith(s: String, part: String): Boolean = s.endsWith(part)
fun stringEquality(a: String, b: String): Boolean = a == b
fun boolEquality(a: Boolean, b: Boolean): Boolean = a == b
