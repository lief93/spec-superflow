package stdliboverloads

fun <T, R> overloadMapped(values: List<T>, transform: (T) -> R): List<R> = values.map(transform)

fun <T> overloadFiltered(values: List<T>, predicate: (T) -> Boolean, negate: Boolean): List<T> =
    if (negate) values.filterNot(predicate) else values.filter(predicate)

fun <T> overloadCursor(values: List<T>): Iterator<T> = values.iterator()
