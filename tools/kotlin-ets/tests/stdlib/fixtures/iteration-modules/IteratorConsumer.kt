package iterationmodules

fun <T> consumeNext(iterator: Iterator<T>): T = iterator.next()
fun consumePair(iterator: Iterator<Int>): Int {
    val first = iterator.next()
    val second = iterator.next()
    return first * 10 + second
}
