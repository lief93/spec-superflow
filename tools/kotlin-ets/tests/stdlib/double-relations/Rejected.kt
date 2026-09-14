package relationnegative

fun floating(left: Float, right: Float): Boolean = left > right
fun wide(left: Long, right: Long): Boolean = left > right
fun total(left: Double, right: Double): Int = left.compareTo(right)
fun equality(left: Double, right: Double): Boolean = left == right
fun boxed(left: Number, right: Number): Boolean = left == right
fun <T> generic(left: T, right: T): Boolean = left == right
