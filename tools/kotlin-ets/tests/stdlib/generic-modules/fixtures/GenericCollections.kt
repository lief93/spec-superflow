package genericmodules

fun <T, R> transformList(values: List<T>, transform: (T) -> R): List<R> = values.map(transform)
fun <T, R> transformIterable(values: Iterable<T>, transform: (T) -> R): List<R> = values.map(transform)
fun <T> retainList(values: Iterable<T>, predicate: (T) -> Boolean): List<T> = values.filter(predicate)
fun <T> rejectList(values: List<T>, predicate: (T) -> Boolean): List<T> = values.filterNot(predicate)
fun <T> listCursor(values: List<T>): Iterator<T> = values.iterator()
fun <T> arrayCursor(values: Array<T>): Iterator<T> = values.iterator()
fun <T> arrayElement(values: Array<T>, index: Int): T = values[index]
fun <T> replaceElement(values: Array<T>, index: Int, value: T) { values[index] = value }
