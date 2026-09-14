package stdliboverloads

fun <T> overloadNext(cursor: Iterator<T>): T = cursor.next()
fun <T> overloadMore(cursor: Iterator<T>): Boolean = cursor.hasNext()
