package nullequalitycases

fun <T> missing(value: T): Boolean = value == null
fun <T> nullFirst(value: T?): Boolean = null == value
fun <T> present(value: T?): Boolean = value != null
fun choose(value: Int?, fallback: Int): Int = value ?: fallback
fun safeLength(value: String?): Int = value?.length ?: -1
fun missingObject(value: Any?): Boolean = value == null
private fun candidate(value: Int?, log: MutableList<Int>): Int? { log.add(1); return value }
private fun fallback(log: MutableList<Int>): Int { log.add(2); return 7 }
fun chooseLogged(value: Int?, log: MutableList<Int>): Int = candidate(value, log) ?: fallback(log)
