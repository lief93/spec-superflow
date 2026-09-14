package genericmethods

class MethodConsumer {
    fun <R> next(cursor: Iterator<R>): R = cursor.next()
    fun <R> more(cursor: Iterator<R>): Boolean = cursor.hasNext()
}
