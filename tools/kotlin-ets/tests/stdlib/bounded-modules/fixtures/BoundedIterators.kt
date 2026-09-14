package boundedmodules

fun <R, T : BoundedReadable<R>> boundedCursor(values: List<T>): Iterator<T> = values.iterator()
fun <R, T : BoundedReadable<R>> nextRead(cursor: Iterator<T>): R = cursor.next().read()
fun <T : BoundedReadable<Int>> keptCursor(values: List<T>): Iterator<T> = boundedCursor<Int, T>(retainPositive(values))
fun <T : BoundedBase> classCursor(values: List<T>): Iterator<T> = values.iterator()
fun <T : BoundedBase> nextClass(cursor: Iterator<T>): Int = cursor.next().read()
