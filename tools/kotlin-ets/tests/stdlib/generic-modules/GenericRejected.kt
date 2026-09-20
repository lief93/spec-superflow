package genericrejected

fun <T, R> arrayMap(values: Array<T>, transform: (T) -> R): List<R> = values.map(transform)
fun <T> arrayFilter(values: Array<T>, predicate: (T) -> Boolean): List<T> = values.filter(predicate)
fun <T, R> sequenceMap(values: Sequence<T>, transform: (T) -> R): Sequence<R> = values.map(transform)
fun <T> projectedFilter(values: List<*>, predicate: (Any?) -> Boolean): List<Any?> = values.filter(predicate)

class SameNames<T> {
    fun map(transform: (T) -> T): List<T> = listOf()
    fun filter(predicate: (T) -> Boolean): List<T> = listOf()
}
fun <T> sourceMap(values: SameNames<T>, transform: (T) -> T): List<T> = values.map(transform)
fun <T> sourceFilter(values: SameNames<T>, predicate: (T) -> Boolean): List<T> = values.filter(predicate)
