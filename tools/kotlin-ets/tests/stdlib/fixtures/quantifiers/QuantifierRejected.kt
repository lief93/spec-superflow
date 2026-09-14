package quantifierrejected

fun arrayAny(values: Array<Int>): Boolean = values.any { it > 0 }
fun intArrayAll(values: IntArray): Boolean = values.all { it > 0 }
fun stringNone(values: String): Boolean = values.none { it == 'x' }
fun sequenceCount(values: Sequence<Int>): Int = values.count { it > 0 }
fun collectionAny(values: Collection<Int>): Boolean = values.any { it > 0 }
fun noPredicateAny(values: Iterable<Int>): Boolean = values.any()
fun noPredicateNone(values: Iterable<Int>): Boolean = values.none()
fun noPredicateCount(values: Iterable<Int>): Int = values.count()
fun widenedPredicate(values: List<Int>, predicate: (Number) -> Boolean): Boolean = values.any(predicate)
class Shadow { fun any(predicate: (Int) -> Boolean): Boolean = predicate(5) }
fun memberAny(value: Shadow): Boolean = value.any { it > 0 }
fun List<Int>.count(predicate: (Int) -> Boolean): Int = 99
fun sourceCount(values: List<Int>): Int = values.count { it > 0 }
