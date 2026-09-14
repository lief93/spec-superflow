package genericmodules

fun <T> consumeNext(cursor: Iterator<T>): T = cursor.next()
fun <T> cursorMore(cursor: Iterator<T>): Boolean = cursor.hasNext()
fun <T, R> mappedCursor(values: List<T>, transform: (T) -> R, predicate: (R) -> Boolean): Iterator<R> =
    listCursor(retainList(transformList(values, transform), predicate))
fun <T> preserved(values: List<T>): List<T> = retainList(transformList(values) { it }) { true }
