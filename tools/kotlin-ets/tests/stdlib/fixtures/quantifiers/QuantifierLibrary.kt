package quantifiercases

fun <T> anyMatch(values: Iterable<T>, predicate: (T) -> Boolean): Boolean = values.any(predicate)
fun <T> allMatch(values: Iterable<T>, predicate: (T) -> Boolean): Boolean = values.all(predicate)
fun <T> noneMatch(values: Iterable<T>, predicate: (T) -> Boolean): Boolean = values.none(predicate)
fun <T> countMatches(values: Iterable<T>, predicate: (T) -> Boolean): Int = values.count(predicate)
fun listAny(values: List<Int>, predicate: (Int) -> Boolean): Boolean = values.any(predicate)
fun mutableAll(values: MutableList<Int>, predicate: (Int) -> Boolean): Boolean = values.all(predicate)

private fun source(log: MutableList<Int>): List<Int> { log.add(10); return listOf(1, 2, 3) }
private fun predicate(log: MutableList<Int>): (Int) -> Boolean {
    log.add(20)
    return { value -> log.add(value); value == 2 }
}
fun orderedAny(log: MutableList<Int>): Boolean = source(log).any(predicate(log))
